#!/usr/bin/env python3
"""
cli.py -- Point d'entree en ligne de commande.
"""

import argparse
import logging
import sys
import time

from config import settings
from core import database


def setup_logging(verbose: bool = False) -> None:
    niveau = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=niveau,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(settings.log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def banniere() -> None:
    print("=" * 70)
    print("  AGENT IA - SUPERVISION ZABBIX NIVEAU 1")
    print("=" * 70)
    print(f"  Mode       : {settings.mode_label}")
    print(f"  LLM        : {settings.llm_model}")
    print(f"  Endpoint   : {settings.llm_base_url}")
    print(f"  Zabbix     : {settings.zabbix_url}")
    print(f"  Seuil ACK  : severite <= {settings.max_auto_ack_severity}")
    print(f"  E-mail     : {'actif' if settings.notify_email_enabled else 'desactive'}")
    print("=" * 70)
    print()


def commande_check() -> int:
    from core import llm_client
    from core import zabbix_tools

    print("Verification des connexions...\n")

    zbx = zabbix_tools.check_connection()
    if zbx["ok"]:
        print(f"  [OK]     Zabbix -- API version {zbx['version']}")
    else:
        print(f"  [ECHEC]  Zabbix -- {zbx['error']}")

    llm = llm_client.check_connection()
    if llm["ok"]:
        print(f"  [OK]     LLM -- {llm['model']} repond correctement")
    else:
        print(f"  [ECHEC]  LLM -- {llm['error']}")

    print()
    if zbx["ok"] and llm["ok"]:
        print("Tout est operationnel. L'agent peut demarrer.")
        return 0
    print("Corriger les erreurs ci-dessus avant de lancer l'agent.")
    return 1


def afficher_resultat(resultat: dict) -> None:
    icone = "[ACK]" if resultat["action"] == "ACKNOWLEDGE" else "[ESCALADE]"
    simulation = " (simulation)" if resultat["dry_run"] else ""

    print(f"\n{icone}{simulation}  event {resultat['eventid']} sur {resultat['hostname']}")
    print(f"  Famille    : {resultat['family']}")
    print(f"  Message    : {resultat['message']}")
    print(f"  Confiance  : {resultat['confidence']:.0%}")
    print(f"  Traite en  : {resultat['steps']} etapes / {resultat['duration_ms']} ms")


def commande_once(verbose: bool) -> int:
    from core.agent import process_all_new

    print("Recherche des alertes non traitees...\n")
    resultats = process_all_new(verbose=verbose)

    if not resultats:
        print("Aucune nouvelle alerte a traiter.")
        return 0

    for resultat in resultats:
        afficher_resultat(resultat)

    acquittees = sum(1 for r in resultats if r["action"] == "ACKNOWLEDGE")
    print(f"\n{len(resultats)} alerte(s) traitee(s) : {acquittees} acquittee(s), {len(resultats) - acquittees} escaladee(s).")
    return 0


def commande_watch(verbose: bool) -> int:
    from core.agent import process_all_new

    print(f"Surveillance active. Scrutation toutes les {settings.poll_interval} s.")
    print("Arret : Ctrl+C\n")

    try:
        while True:
            try:
                resultats = process_all_new(verbose=verbose)
                for resultat in resultats:
                    afficher_resultat(resultat)
                if not resultats:
                    print(f"[{time.strftime('%H:%M:%S')}] Aucune nouvelle alerte.")
            except Exception as exc:
                logging.error("Erreur pendant la scrutation : %s", exc)

            time.sleep(settings.poll_interval)
    except KeyboardInterrupt:
        print("\nSurveillance interrompue.")
        return 0


def commande_eventid(eventid: str, verbose: bool) -> int:
    from core.agent import process_event

    try:
        resultat = process_event(eventid, verbose=verbose)
        afficher_resultat(resultat)
        return 0
    except ValueError as exc:
        print(f"Erreur : {exc}")
        return 1


def main() -> int:
    parseur = argparse.ArgumentParser(
        description="Agent IA de supervision Zabbix niveau 1",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    groupe = parseur.add_mutually_exclusive_group(required=True)
    groupe.add_argument("--check", action="store_true", help="verifier les connexions Zabbix et LLM")
    groupe.add_argument("--once", action="store_true", help="traiter une fois les alertes non traitees")
    groupe.add_argument("--watch", action="store_true", help="surveiller en continu")
    groupe.add_argument("--eventid", type=str, metavar="ID", help="traiter un evenement precis")

    parseur.add_argument("--verbose", "-v", action="store_true", help="afficher le raisonnement etape par etape")
    parseur.add_argument("--live", action="store_true", help="desactiver le dry-run pour cette execution (actions reelles)")

    arguments = parseur.parse_args()

    if arguments.live:
        settings.dry_run = False

    setup_logging(arguments.verbose)
    database.init_db()
    banniere()

    if arguments.check:
        return commande_check()
    if arguments.once:
        return commande_once(arguments.verbose)
    if arguments.watch:
        return commande_watch(arguments.verbose)
    if arguments.eventid:
        return commande_eventid(arguments.eventid, arguments.verbose)
    return 1


if __name__ == "__main__":
    sys.exit(main())
