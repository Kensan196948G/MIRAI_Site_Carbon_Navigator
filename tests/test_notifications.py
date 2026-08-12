"""Tests for SMTP/Teams notification delivery."""
import json

from app.services import notify


class _FakeSMTP:
    def __init__(self, host, port, timeout=15):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.credentials = None
        self.messages = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, username, password):
        self.credentials = (username, password)

    def send_message(self, message):
        self.messages.append(message)


class _FakeResponse:
    def __init__(self, status):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_send_email_success(monkeypatch):
    monkeypatch.setenv("MIRAI_SMTP_HOST", "smtp.office365.com")
    monkeypatch.setenv("MIRAI_SMTP_PORT", "587")
    monkeypatch.setenv("MIRAI_SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("MIRAI_SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("MIRAI_SMTP_FROM", "noreply@example.com")

    fake = _FakeSMTP("smtp.office365.com", 587)
    monkeypatch.setattr(notify.smtplib, "SMTP", lambda *a, **k: fake)

    ok = notify.send_email(
        ["admin@example.com"],
        "通知試験",
        "本文",
    )
    assert ok is True
    assert fake.started_tls is True
    assert fake.credentials == ("noreply@example.com", "app-password")
    assert fake.messages and fake.messages[0]["To"] == "admin@example.com"


def test_send_email_returns_false_without_host(monkeypatch):
    monkeypatch.delenv("MIRAI_SMTP_HOST", raising=False)
    assert notify.send_email(["a@example.com"], "t", "b") is False


def test_send_teams_success(monkeypatch):
    webhook = "https://example.webhook.office.com/webhookb2/test"
    monkeypatch.setenv("MIRAI_TEAMS_WEBHOOK", webhook)
    captured = {}

    def fake_urlopen(request, timeout=15):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(200)

    monkeypatch.setattr(notify.url_request, "urlopen", fake_urlopen)

    assert notify.send_teams("通知試験") is True
    assert captured["url"] == webhook
    assert captured["payload"] == {"text": "通知試験"}


def test_send_teams_returns_false_without_webhook(monkeypatch):
    monkeypatch.delenv("MIRAI_TEAMS_WEBHOOK", raising=False)
    assert notify.send_teams("通知試験") is False
