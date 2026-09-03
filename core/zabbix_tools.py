import logging
from zabbix_utils import ZabbixAPI
from config import settings

logger = logging.getLogger(__name__)
_api: ZabbixAPI | None = None


def get_api() -> ZabbixAPI:
    global _api
    if _api is None:
        _api = ZabbixAPI(
            url=settings.zabbix_url,
            token=settings.zabbix_token,
            validate_certs=settings.zabbix_verify_ssl,
        )
        logger.info("Connexion Zabbix etablie (API v%s)", _api.api_version())
    return _api


def check_connection() -> dict:
    try:
        api = get_api()
        return {"ok": True, "version": str(api.api_version())}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def get_active_problems(hostname: str | None = None, limit: int = 20) -> list[dict]:
    api = get_api()
    params: dict = {
        "output": ["eventid", "name", "severity", "clock", "objectid", "acknowledged"],
        "sortfield": ["eventid"],
        "sortorder": "DESC",
        "limit": limit,
        "recent": False,
        "suppressed": True,
    }
    if hostname:
        hosts = api.host.get(filter={"host": hostname}, output=["hostid"])
        if not hosts:
            return []
        params["hostids"] = [h["hostid"] for h in hosts]
    problems = api.problem.get(**params)
    trigger_ids = [p["objectid"] for p in problems]
    host_by_trigger: dict[str, str] = {}
    if trigger_ids:
        triggers = api.trigger.get(
            triggerids=trigger_ids,
            output=["triggerid"],
            selectHosts=["host"],
        )
        for t in triggers:
            if t.get("hosts"):
                host_by_trigger[t["triggerid"]] = t["hosts"][0]["host"]
    return [
        {
            "eventid": p["eventid"],
            "name": p["name"],
            "severity": int(p["severity"]),
            "clock": int(p["clock"]),
            "acknowledged": p.get("acknowledged") == "1",
            "hostname": host_by_trigger.get(p["objectid"], "inconnu"),
        }
        for p in problems
    ]


def get_host_context(hostname: str) -> dict:
    api = get_api()
    hosts = api.host.get(
        filter={"host": hostname},
        output=["hostid", "host", "name", "status", "maintenance_status"],
        selectHostGroups=["name"],
        selectInterfaces=["ip", "available"],
    )
    if not hosts:
        return {"found": False, "hostname": hostname}
    h = hosts[0]
    return {
        "found": True,
        "hostid": h["hostid"],
        "hostname": h["host"],
        "display_name": h.get("name", h["host"]),
        "en_maintenance": h.get("maintenance_status") == "1",
        "surveille": h.get("status") == "0",
        "groupes": [g["name"] for g in h.get("hostgroups", [])],
        "ip": h["interfaces"][0]["ip"] if h.get("interfaces") else None,
    }


def get_metric_history(hostname: str, key_search: str, limit: int = 10) -> dict:
    api = get_api()
    hosts = api.host.get(filter={"host": hostname}, output=["hostid"])
    if not hosts:
        return {"found": False, "raison": f"hote '{hostname}' introuvable"}
    items = api.item.get(
        hostids=hosts[0]["hostid"],
        search={"key_": key_search},
        output=["itemid", "name", "key_", "value_type", "lastvalue", "units"],
        limit=5,
    )
    if not items:
        return {"found": False, "raison": f"aucune metrique '{key_search}' sur cet hote"}
    item = items[0]
    history = api.history.get(
        itemids=item["itemid"],
        history=int(item["value_type"]),
        output="extend",
        sortfield="clock",
        sortorder="DESC",
        limit=limit,
    )
    valeurs = [float(h["value"]) for h in history if h.get("value") is not None]
    return {
        "found": True,
        "metrique": item["name"],
        "cle": item["key_"],
        "unite": item.get("units", ""),
        "derniere_valeur": item.get("lastvalue"),
        "valeurs_recentes": valeurs,
        "moyenne": round(sum(valeurs) / len(valeurs), 2) if valeurs else None,
        "maximum": max(valeurs) if valeurs else None,
        "minimum": min(valeurs) if valeurs else None,
    }


def acknowledge_event(eventid: str, message: str, severity: int = 0) -> dict:
    if severity > settings.max_auto_ack_severity:
        logger.warning(
            "Acquittement REFUSE : severite %s > seuil autorise %s",
            severity, settings.max_auto_ack_severity,
        )
        return {
            "success": False,
            "refuse": True,
            "raison": (
                f"Severite {severity} superieure au seuil autorise "
                f"({settings.max_auto_ack_severity})."
            ),
        }
    if settings.dry_run:
        logger.info("[DRY-RUN] Acquittement simule sur l'evenement %s", eventid)
        return {
            "success": True,
            "dry_run": True,
            "action_simulee": "acknowledge",
            "eventid": eventid,
            "message": message,
            "note": "Mode simulation : aucune ecriture dans Zabbix.",
        }
    api = get_api()
    result = api.event.acknowledge(eventids=eventid, action=6, message=message)
    logger.info("Evenement %s acquitte dans Zabbix", eventid)
    return {"success": True, "dry_run": False, "eventid": eventid, "resultat": result}


def escalate_event(eventid: str, message: str, hostname: str = "", problem: str = "") -> dict:
    texte = f"[ESCALADE N2 par agent IA] {message}"
    if settings.dry_run:
        logger.info("[DRY-RUN] Escalade simulee sur l'evenement %s", eventid)
        resultat = {
            "success": True,
            "dry_run": True,
            "action_simulee": "escalate",
            "eventid": eventid,
            "message": texte,
            "note": "Mode simulation : aucune ecriture dans Zabbix.",
        }
    else:
        api = get_api()
        result = api.event.acknowledge(eventids=eventid, action=4, message=texte)
        logger.info("Evenement %s escalade", eventid)
        resultat = {
            "success": True,
            "dry_run": False,
            "eventid": eventid,
            "resultat": result,
        }
    if settings.notify_email_enabled:
        from core.notifier import send_escalation_email
        envoye = send_escalation_email(
            eventid=eventid, hostname=hostname, problem=problem, reason=message
        )
        resultat["email_envoye"] = envoye
    return resultat
