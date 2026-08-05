"""External notification delivery: SMTP email and Microsoft Teams webhook."""
import logging
import os
import smtplib
from email.message import EmailMessage
from urllib import request as url_request

logger = logging.getLogger(__name__)


def _smtp_config():
    host = os.getenv("MIRAI_SMTP_HOST")
    if not host:
        return None
    return {
        "host": host,
        "port": int(os.getenv("MIRAI_SMTP_PORT", "587")),
        "username": os.getenv("MIRAI_SMTP_USER", ""),
        "password": os.getenv("MIRAI_SMTP_PASSWORD", ""),
        "from": os.getenv("MIRAI_SMTP_FROM", "noreply@mirai-carbon.local"),
        "use_tls": os.getenv("MIRAI_SMTP_TLS", "1") == "1",
    }


def send_email(to_addresses: list[str], subject: str, body: str) -> bool:
    config = _smtp_config()
    if not config or not to_addresses:
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = config["from"]
        msg["To"] = ", ".join(to_addresses)
        msg.set_content(body)
        with smtplib.SMTP(config["host"], config["port"], timeout=15) as server:
            if config["use_tls"]:
                server.starttls()
            if config["username"]:
                server.login(config["username"], config["password"])
            server.send_message(msg)
        return True
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("SMTP send failed: %s", exc)
        return False


def send_teams(text: str) -> bool:
    webhook = os.getenv("MIRAI_TEAMS_WEBHOOK")
    if not webhook:
        return False
    try:
        payload = '{"text": ' + __import__("json").dumps(text) + "}"
        req = url_request.Request(
            webhook,
            data=payload.encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with url_request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Teams webhook failed: %s", exc)
        return False


def deliver_external(
    db,
    message: str,
    recipient_role: str | None = None,
    recipient_username: str | None = None,
) -> None:
    """Deliver a notification to email/Teams when configured."""
    from .. import crud

    recipients = []
    if recipient_username:
        user = crud.get_user_by_username(db, recipient_username)
        if user and user.email:
            recipients.append(user)
    elif recipient_role:
        for user in crud.list_users(db):
            if user.role == recipient_role and user.email:
                recipients.append(user)

    emails = [u.email for u in recipients if u.email]
    if emails:
        send_email(emails, f"[MIRAI Carbon Navigator] {message[:60]}", message)
    send_teams(f"🌿 {message}")
