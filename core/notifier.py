import logging
import smtplib
from email.message import EmailMessage
from datetime import datetime
from config import settings

logger = logging.getLogger(__name__)


def send_escalation_email(eventid: str, hostname: str, problem: str, reason: str) -> bool:
    if not settings.notify_email_enabled:
        return False
    if not settings.smtp_to:
        logger.warning("SMTP_TO non renseigne")
        return False
    horodatage = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = EmailMessage()
    msg["Subject"] = f"[Zabbix N1] Escalade - {hostname} - {problem}"
    msg["From"] = settings.smtp_from
    msg["To"] = settings.smtp_to
    msg.set_content(
        f"Escalade automatique par l'agent IA.\n\n"
        f"Hote       : {hostname}\n"
        f"Probleme   : {problem}\n"
        f"Event ID   : {eventid}\n"
        f"Horodatage : {horodatage}\n\n"
        f"Raison :\n{reason}\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            smtp.ehlo()
            if settings.smtp_port == 587:
                smtp.starttls()
                smtp.ehlo()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(msg)
        logger.info("E-mail envoye a %s", settings.smtp_to)
        return True
    except Exception as exc:
        logger.error("Echec envoi e-mail : %s", exc)
        return False


def test_email() -> dict:
    ok = send_escalation_email(
        eventid="TEST-0000",
        hostname="host-de-test",
        problem="Test SMTP",
        reason="Test depuis la console web.",
    )
    return {
        "ok": ok,
        "destinataire": settings.smtp_to,
        "serveur": f"{settings.smtp_host}:{settings.smtp_port}",
    }
