from app.services.adaptive_auth import select_factor
from app.services.policy import DEFAULT_POLICY

STEPUP = DEFAULT_POLICY["stepup"]


def test_light_prefers_mpin_over_otp_when_both_available():
    step_up = select_factor("light", {"MPIN", "OTP"}, STEPUP)
    assert step_up.challenge_type == "MPIN"
    assert step_up.assurance == "light"


def test_light_falls_back_to_otp_when_mpin_unavailable():
    step_up = select_factor("light", {"OTP"}, STEPUP)
    assert step_up.challenge_type == "OTP"


def test_strong_prefers_fingerprint_as_second_factor_when_available():
    # "strong" assurance = sequential 2FA: OTP first (challenge_type), FINGERPRINT second.
    # The biometric is carried in second_factor, not challenge_type.
    step_up = select_factor("strong", {"FINGERPRINT", "PASSKEY", "OTP"}, STEPUP)
    assert step_up.challenge_type == "OTP"
    assert step_up.second_factor == "FINGERPRINT"
    assert step_up.assurance == "strong"


def test_strong_falls_back_to_otp_only_without_biometric():
    # VOICE_READBACK is not a FIDO-class biometric; when no FINGERPRINT/PASSKEY is
    # available the strong flow degrades to OTP-only (no second factor).
    step_up = select_factor("strong", {"OTP", "MPIN", "VOICE_READBACK"}, STEPUP)
    assert step_up.challenge_type == "OTP"
    assert step_up.second_factor is None


def test_strong_uses_passkey_as_second_factor_when_no_fingerprint():
    # PASSKEY is the FIDO-class biometric when FINGERPRINT is absent.
    # The first step is still OTP; PASSKEY comes as second_factor.
    step_up = select_factor("strong", {"OTP", "MPIN", "PASSKEY"}, STEPUP)
    assert step_up.challenge_type == "OTP"
    assert step_up.second_factor == "PASSKEY"


def test_strong_degrades_upward_only_when_nothing_clears_the_bar():
    # Device truly only supports OTP/MPIN -- never below band strength silently, but
    # there is nothing higher to pick, so the strongest of what's available is used.
    step_up = select_factor("strong", {"OTP", "MPIN"}, STEPUP)
    assert step_up.challenge_type in ("OTP", "MPIN")


def test_unknown_device_caps_assumes_universal_otp_mpin():
    step_up = select_factor("light", None, STEPUP)
    assert step_up.challenge_type in ("OTP", "MPIN")


def test_challenge_id_is_unique_per_call():
    a = select_factor("light", {"OTP"}, STEPUP)
    b = select_factor("light", {"OTP"}, STEPUP)
    assert a.challenge_id != b.challenge_id
