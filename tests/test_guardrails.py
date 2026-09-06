"""
Tests des GARDE-FOUS -- le cœur de la sécurité de l'agent.

On vérifie deux garanties, indépendamment du LLM :
1. Le seuil de sévérité : au-delà du seuil, l'acquittement est REFUSÉ.
2. Le mode dry-run : aucun appel réel à l'API Zabbix quand DRY_RUN=true.
"""
from core.zabbix_tools import acknowledge_event


# ---------------------------------------------------------------------------
# 1. SEUIL DE SÉVÉRITÉ
# ---------------------------------------------------------------------------

def test_ack_refuse_au_dessus_du_seuil(mock_api, set_guardrails):
    """Sévérité 4 (High) > seuil 2 (Warning) -> acquittement refusé, sans API."""
    set_guardrails(dry_run=False, max_auto_ack_severity=2)
    result = acknowledge_event("12345", "tentative d'acquittement", severity=4)
    assert result["success"] is False
    assert result["refuse"] is True
    mock_api.event.acknowledge.assert_not_called()


def test_ack_autorise_au_seuil_appelle_l_api(mock_api, set_guardrails):
    """Sévérité 2 == seuil, mode réel -> l'API est bien appelée avec action=6."""
    set_guardrails(dry_run=False, max_auto_ack_severity=2)
    result = acknowledge_event("12345", "cas benin", severity=2)
    assert result["success"] is True
    assert result["dry_run"] is False
    mock_api.event.acknowledge.assert_called_once()
    _, kwargs = mock_api.event.acknowledge.call_args
    assert kwargs.get("action") == 6


def test_ack_severite_disaster_toujours_refusee(mock_api, set_guardrails):
    """Sévérité 5 (Disaster) -> toujours refusée, quel que soit le reste."""
    set_guardrails(dry_run=False, max_auto_ack_severity=2)
    result = acknowledge_event("999", "grosse alerte", severity=5)
    assert result["refuse"] is True
    mock_api.event.acknowledge.assert_not_called()


# ---------------------------------------------------------------------------
# 2. MODE DRY-RUN
# ---------------------------------------------------------------------------

def test_dry_run_aucun_appel_reel(mock_api, set_guardrails):
    """DRY_RUN=true -> décision simulée, ZÉRO appel à l'API Zabbix."""
    set_guardrails(dry_run=True, max_auto_ack_severity=2)
    result = acknowledge_event("12345", "cas benin", severity=1)
    assert result["success"] is True
    assert result["dry_run"] is True
    assert result["action_simulee"] == "acknowledge"
    mock_api.event.acknowledge.assert_not_called()


def test_dry_run_prioritaire_meme_sous_le_seuil(mock_api, set_guardrails):
    """Même une alerte parfaitement acquittable n'écrit rien en dry-run."""
    set_guardrails(dry_run=True, max_auto_ack_severity=3)
    acknowledge_event("777", "warning transitoire", severity=2)
    mock_api.event.acknowledge.assert_not_called()
