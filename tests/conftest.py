"""
Fixtures partagees.

Principe : AUCUN test ne doit dependre d'un vrai serveur Zabbix. On remplace
donc l'acces a l'API (`get_api`) par un mock, et on pilote les garde-fous
(`dry_run`, `max_auto_ack_severity`) via la configuration.
"""
from unittest.mock import MagicMock

import pytest

import config
import core.zabbix_tools as zt


@pytest.fixture
def mock_api(monkeypatch):
    """Remplace l'acces reel a Zabbix par un mock.

    Toute tentative d'ecriture reelle passerait par api.event.acknowledge :
    on pourra donc verifier si elle a ete appelee ou non.
    """
    api = MagicMock()
    monkeypatch.setattr(zt, "get_api", lambda: api)
    monkeypatch.setattr(zt, "_api", None, raising=False)
    return api


@pytest.fixture
def set_guardrails(monkeypatch):
    """Helper pour fixer l'etat des garde-fous dans un test."""
    def _apply(dry_run=False, max_auto_ack_severity=2, notify_email_enabled=False):
        monkeypatch.setattr(config.settings, "dry_run", dry_run)
        monkeypatch.setattr(config.settings, "max_auto_ack_severity", max_auto_ack_severity)
        monkeypatch.setattr(config.settings, "notify_email_enabled", notify_email_enabled)
    return _apply
