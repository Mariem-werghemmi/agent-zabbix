#!/usr/bin/env python3
"""
web.py -- Console web de supervision (FastAPI).
Comme cli.py, ce fichier ne contient AUCUNE logique de decision : il appelle
le meme moteur core.agent. C'est ce qui permet de livrer les deux formats
demandes (script + console web) sans ecrire la logique deux fois.
Role de la console (critere de reussite valide avec l'encadrant) :
- afficher les alertes actives de Zabbix
- lancer l'agent sur une alerte et montrer son RAISONNEMENT en direct
- presenter l'historique des decisions et les statistiques d'evaluation
Lancement :
python web.py
# puis ouvrir http://<IP-VM-AGENT>:8000
"""
import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import BASE_DIR, settings
from core import database, llm_client, zabbix_tools
from core.agent import process_event
from core.schemas import SEVERITY_LABELS

# ---------------------------------------------------------------------------
# Journalisation
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(settings.log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Agent IA - Supervision Zabbix N1",
    description="Console de supervision et de tracabilite des decisions de l'agent",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def au_demarrage() -> None:
    """Cree la base si besoin et journalise la configuration active."""
    database.init_db()
    logger.info("Console web demarree -- mode %s", settings.mode_label)


# ===========================================================================
# PAGE PRINCIPALE
# ===========================================================================
@app.get("/", response_class=HTMLResponse)
def tableau_de_bord(request: Request):
    """Tableau de bord : etat des connexions, alertes actives, historique."""
    etat_zabbix = zabbix_tools.check_connection()

    if etat_zabbix["ok"]:
        try:
            alertes = zabbix_tools.get_active_problems(limit=30)
        except Exception as exc:
            logger.error("Lecture des alertes impossible : %s", exc)
            alertes = []
    else:
        alertes = []

    # Marque les alertes deja traitees pour ne pas les relancer inutilement
    for alerte in alertes:
        alerte["deja_traite"] = database.already_processed(alerte["eventid"])
        alerte["severity_label"] = SEVERITY_LABELS.get(alerte["severity"], "Inconnue")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "alertes": alertes,
            "decisions": database.get_recent_decisions(limit=25),
            "stats": database.get_stats(),
            "etat_zabbix": etat_zabbix,
            "settings": settings,
            "severites": SEVERITY_LABELS,
        },
    )


# ===========================================================================
# API JSON -- utilisee par le JavaScript de la page
# ===========================================================================
@app.post("/api/analyser/{eventid}")
def analyser(eventid: str):
    """Lance l'agent sur une alerte et renvoie sa decision + son raisonnement.

    C'est l'appel central de la demonstration : l'utilisateur clique sur
    "Analyser", et la trace complete du raisonnement s'affiche.
    """
    try:
        resultat = process_event(eventid)
        return JSONResponse(resultat)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except Exception as exc:
        logger.exception("Echec de l'analyse de l'evenement %s", eventid)
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/alertes")
def api_alertes():
    """Liste des alertes actives, au format JSON."""
    try:
        alertes = zabbix_tools.get_active_problems(limit=30)
        for alerte in alertes:
            alerte["deja_traite"] = database.already_processed(alerte["eventid"])
        return JSONResponse(alertes)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@app.get("/api/decisions")
def api_decisions(limit: int = 25):
    """Historique des decisions, au format JSON."""
    return JSONResponse([d.model_dump() for d in database.get_recent_decisions(limit)])


@app.get("/api/decision/{decision_id}")
def api_decision(decision_id: int):
    """Detail d'une decision precise."""
    decision = database.get_decision(decision_id)
    if decision is None:
        return JSONResponse({"error": "Decision introuvable"}, status_code=404)
    return JSONResponse(decision.model_dump())


@app.get("/api/stats")
def api_stats():
    """Statistiques agregees (support du critere de reussite)."""
    return JSONResponse(database.get_stats())


@app.get("/api/sante")
def api_sante():
    """Etat des dependances externes : Zabbix et LLM."""
    return JSONResponse(
        {
            "zabbix": zabbix_tools.check_connection(),
            "llm": llm_client.check_connection(),
            "mode": settings.mode_label,
            "dry_run": settings.dry_run,
        }
    )


# ===========================================================================
if __name__ == "__main__":
    uvicorn.run(
        "web:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=False,
    )











