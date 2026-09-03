import json
import logging
import time
from datetime import datetime

from config import settings
from core import database, llm_client
from core.schemas import Action, AlertContext, AlertFamily, Decision, DecisionRecord
from core.tools_schema import DISPATCH, TERMINAL_TOOLS, TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un agent de supervision Zabbix de NIVEAU 1.
Ton role : trier les alertes, diagnostiquer les cas connus, puis DECIDER.
Tu n'interviens JAMAIS sur les systemes eux-memes.

PROCEDURE OBLIGATOIRE
1. Appelle get_host_context pour verifier si l'hote est EN MAINTENANCE.
   Si oui -> acquitte immediatement.
2. Verifie la metrique avec get_metric_history :
   - CPU eleve      -> cle 'cpu.util'
   - Disque plein   -> cle 'vfs.fs.dependent.size'
   - Service arrete -> cherche la cle SPECIFIQUE au service concerne, ex.
   'proc.num[nomservice]' (avec le nom entre crochets). N'utilise PAS
   la cle generique 'proc.num' seule, qui compte TOUS les processus du
   systeme et ne dit rien sur un service precis.
   - Host injoignable -> cle 'icmpping'
3. Appelle EXACTEMENT UN outil : acknowledge_event OU escalate_event.

REGLES
ACQUITTER si TOUTES ces conditions sont reunies :
- hote en maintenance, OU
- la DERNIERE valeur (la plus recente) de la metrique est revenue sous
  le seuil normal ET severite <= 2.
- IMPORTANT : ne te fie JAMAIS a la seule MOYENNE sur une fenetre longue
  pour juger qu'une charge est "revenue a la normale". Une moyenne
  peut masquer une valeur recente encore elevee (ex: 100/100/20/100/56
  donne une moyenne de 56% alors que la charge est toujours critique).
  Compare toujours le DERNIER point releve au seuil, pas la moyenne.
- Exemple correct : max 100%, derniere valeur 12% -> pic transitoire,
  acquitter.
- Exemple incorrect : max 100%, moyenne 56%, derniere valeur inconnue
  ou elevee -> NE PAS acquitter, escalader.

ESCALADER si :
- severite >= 3, OU
- la DERNIERE valeur de la metrique est encore au-dessus du seuil
  (la charge est ACTUELLE, pas seulement passee), OU
- la DERNIERE valeur est EGALE ou PROCHE du MAXIMUM
  (ecart inferieur a 5%) -> la charge est ENCORE ACTIVE,
  ce n'est PAS un pic transitoire.
  Exemple : max 99.99%, derniere 99.99% -> ESCALADER
  Exemple : max 99.96%, derniere 99.96% -> ESCALADER
  Exemple : max 99%, derniere 12%       -> pic transitoire -> ACQUITTER
- hote injoignable, OU
- doute.

REGLE SPECIFIQUE AU DISQUE (famille DISQUE_PLEIN) :
Cette regle remplace la logique "pic transitoire" ci-dessus pour le disque.
- Un disque ne se vide pas seul : ne raisonne JAMAIS en "pic transitoire"
  comme pour le CPU.
- < 85% : situation normale, faux positif probable -> ACQUITTER.
- entre 85 et 90% : surveiller. Si stable, ACQUITTER avec commentaire.
- > 90% : ESCALADER (risque de saturation imminente).
- Si les valeurs recentes AUGMENTENT regulierement -> ESCALADER meme
  en dessous de 90%, car la tendance est mauvaise.

Dans le doute, ESCALADE TOUJOURS.
Redige en francais, cite les chiffres reels observes.
"""

def run_agent(alert: AlertContext, verbose: bool = False) -> dict:
    debut = time.time()
    messages: list = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": alert.to_prompt()},
    ]

    trace: list[dict] = []
    decision: Decision | None = None
    etapes = 0

    for etape in range(settings.llm_max_steps):
        etapes = etape + 1
        try:
            message = llm_client.chat(messages, tools=TOOLS)
        except Exception as exc:
            logger.error("Erreur LLM : %s", exc)
            trace.append({"type": "erreur", "contenu": str(exc)})
            decision = _decision_de_repli(f"Erreur LLM : {exc}")
            break

        messages.append(message)

        if message.content:
            if verbose:
                print(f"  [Pensee {etapes}] {message.content[:200]}")
            trace.append({"type": "pensee", "contenu": message.content})

        if not message.tool_calls:
            decision = _decision_de_repli("Aucun outil de decision appele.")
            break

        decision_prise = False
        for appel in message.tool_calls:
            nom = appel.function.name
            if nom not in DISPATCH:
                resultat = {"error": f"Outil inconnu : {nom}"}
                arguments = {}
            else:
                try:
                    arguments = json.loads(appel.function.arguments or "{}")
                except json.JSONDecodeError as exc:
                    resultat = {"error": f"JSON invalide : {exc}"}
                    arguments = {}
                else:
                    if verbose:
                        print(f"  [Action {etapes}] {nom}({arguments})")
                    try:
                        resultat = DISPATCH[nom](**arguments)
                    except Exception as exc:
                        logger.warning("Erreur outil %s : %s", nom, exc)
                        resultat = {"error": str(exc)}

            trace.append({"type": "action", "outil": nom, "arguments": arguments})
            trace.append({"type": "observation", "outil": nom, "resultat": resultat})

            if verbose:
                print(f"  [Observation] {json.dumps(resultat, ensure_ascii=False, default=str)[:200]}")

            messages.append({
                "role": "tool",
                "tool_call_id": appel.id,
                "content": json.dumps(resultat, ensure_ascii=False, default=str),
            })

            if nom in TERMINAL_TOOLS and resultat.get("success"):
                decision = _construire_decision(nom, arguments, alert)
                decision_prise = True
            elif nom == "acknowledge_event" and resultat.get("refuse"):
                logger.info("Acquittement refuse par seuil")

        if decision_prise:
            break

    if decision is None:
        decision = _decision_de_repli(f"Limite de {settings.llm_max_steps} etapes atteinte.")

    duree_ms = int((time.time() - debut) * 1000)
    enregistrement = DecisionRecord(
        eventid=alert.eventid,
        hostname=alert.hostname,
        problem_name=alert.name,
        severity=alert.severity,
        action=decision.action.value,
        family=decision.family.value,
        reasoning=decision.reasoning,
        confidence=decision.confidence,
        message=decision.message,
        dry_run=settings.dry_run,
        steps_used=etapes,
        duration_ms=duree_ms,
        llm_model=settings.llm_model,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )
    decision_id = database.save_decision(enregistrement)
    logger.info(
        "Event %s -> %s (%s etapes, %s ms)",
        alert.eventid, decision.action.value, etapes, duree_ms,
    )
    return {
        "decision_id": decision_id,
        "eventid": alert.eventid,
        "hostname": alert.hostname,
        "action": decision.action.value,
        "family": decision.family.value,
        "reasoning": decision.reasoning,
        "message": decision.message,
        "confidence": decision.confidence,
        "steps": etapes,
        "duration_ms": duree_ms,
        "dry_run": settings.dry_run,
        "trace": trace,
    }


def _construire_decision(nom_outil: str, arguments: dict, alert: AlertContext) -> Decision:
    action = Action.ACKNOWLEDGE if nom_outil == "acknowledge_event" else Action.ESCALATE
    message = arguments.get("message", "Aucun message fourni.")
    return Decision(
        action=action,
        family=_deviner_famille(alert.name),
        reasoning=message,
        confidence=0.85 if action == Action.ACKNOWLEDGE else 0.75,
        message=message,
    )


def _decision_de_repli(raison: str) -> Decision:
    return Decision(
        action=Action.ESCALATE,
        family=AlertFamily.UNKNOWN,
        reasoning=f"Escalade automatique. {raison}",
        confidence=0.0,
        message=f"Escalade N2 : l'agent n'a pas pu conclure. {raison}",
    )


def _deviner_famille(nom_probleme: str) -> AlertFamily:
    texte = nom_probleme.lower()
    if any(m in texte for m in ("cpu", "processor", "load")):
        return AlertFamily.CPU
    if any(m in texte for m in ("disk", "disque", "space", "filesystem", "vfs")):
        return AlertFamily.DISK
    if any(m in texte for m in ("service", "process", "proc", "daemon")):
        return AlertFamily.SERVICE
    if any(m in texte for m in ("unreachable", "unavailable", "ping", "down", "icmp")):
        return AlertFamily.HOST_DOWN
    return AlertFamily.UNKNOWN


def process_event(eventid: str, verbose: bool = False) -> dict:
    from core.zabbix_tools import get_active_problems
    problemes = get_active_problems(limit=200)
    correspondance = next(
        (p for p in problemes if p["eventid"] == str(eventid)), None
    )
    if correspondance is None:
        raise ValueError(f"Evenement {eventid} introuvable.")
    alerte = AlertContext(
        eventid=correspondance["eventid"],
        name=correspondance["name"],
        severity=correspondance["severity"],
        hostname=correspondance["hostname"],
        clock=correspondance["clock"],
    )
    return run_agent(alerte, verbose=verbose)


def process_all_new(verbose: bool = False) -> list[dict]:
    from core.zabbix_tools import get_active_problems
    resultats = []
    for probleme in get_active_problems(limit=50):
        if database.already_processed(probleme["eventid"]):
            continue
        alerte = AlertContext(
            eventid=probleme["eventid"],
            name=probleme["name"],
            severity=probleme["severity"],
            hostname=probleme["hostname"],
            clock=probleme["clock"],
        )
        resultats.append(run_agent(alerte, verbose=verbose))
    return resultats
