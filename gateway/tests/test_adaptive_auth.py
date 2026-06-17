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


def test_strong_prefers_fingerprint_when_available():
    step_up = select_factor("strong", {"FINGERPRINT", "PASSKEY", "OTP"}, STEPUP)
    assert step_up.challenge_type == "FINGERPRINT"
    assert step_up.assurance == "strong"


def test_strong_falls_back_to_voice_readback_without_biometric():
    step_up = select_factor("strong", {"OTP", "MPIN", "VOICE_READBACK"}, STEPUP)
    assert step_up.challenge_type == "VOICE_READBACK"


def test_strong_never_returns_otp_or_mpin():
    # Even if OTP/MPIN are the only things in the device's claimed capability set,
    # "strong" must never silently settle for a non-phishing-resistant factor when a
    # better one *could* exist -- it should still surface a strong-tier pick.
    step_up = select_factor("strong", {"OTP", "MPIN", "PASSKEY"}, STEPUP)
    assert step_up.challenge_type == "PASSKEY"


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
