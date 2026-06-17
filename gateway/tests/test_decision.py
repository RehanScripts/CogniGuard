"""Phase 7 acceptance check (Implementation.md lines 467-475)."""

from app.services.decision_engine import decide
from app.services.policy import DEFAULT_POLICY

POLICY = DEFAULT_POLICY


def test_low_band_login_allows():
    d = decide("low", "login", policy=POLICY)
    assert d.action == "allow"


def test_medium_band_login_verifies_light():
    d = decide("medium", "login", policy=POLICY)
    assert d.action == "verify"
    assert d.assurance == "light"


def test_high_band_login_verifies_strong():
    d = decide("high", "login", policy=POLICY)
    assert d.action == "verify"
    assert d.assurance == "strong"


def test_very_high_band_blocks_with_alert():
    d = decide("very_high", "login", policy=POLICY)
    assert d.action == "block"
    assert d.block_alert is True


def test_low_risk_high_stakes_new_payee_verifies_with_cooling_off():
    d = decide("low", "transfer_new_payee_large", policy=POLICY)
    assert d.action == "verify"
    assert d.assurance == "light"
    assert d.cooling_off is True


def test_cold_start_very_high_never_blocks():
    d = decide("very_high", "login", policy=POLICY, cold_start=True)
    assert d.action == "verify"
    assert d.assurance == "strong"


def test_cold_start_high_stakes_block_cell_downgrades_to_verify():
    d = decide("high", "transfer_new_payee_large", policy=POLICY, cold_start=True)
    assert d.action == "verify"
    assert d.assurance == "strong"
    # downgraded controls are preserved, not silently dropped
    assert d.reconfirm is True
    assert d.cooling_off is True


def test_degraded_scoring_upgrades_allow_to_verify_light():
    d = decide("low", "login", policy=POLICY, degraded=True)
    assert d.action == "verify"
    assert d.assurance == "light"


def test_degraded_scoring_does_not_downgrade_existing_verify():
    d = decide("high", "login", policy=POLICY, degraded=True)
    assert d.action == "verify"
    assert d.assurance == "strong"


def test_unknown_action_type_defaults_to_medium_stakes():
    d = decide("medium", "some_unconfigured_action", policy=POLICY)
    assert d.action_sensitivity == "medium"
    assert d.action == "verify"
    assert d.assurance == "light"


def test_high_band_high_stakes_blocks_outright():
    d = decide("high", "raise_limit", policy=POLICY)
    assert d.action == "block"
    assert d.reconfirm is True
    assert d.cooling_off is True
