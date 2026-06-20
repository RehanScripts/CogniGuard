"""BehaviorPayload (client → gateway) — Architecture §5.1.

Accepts EITHER raw modality blocks (web) OR `derived_features` (mobile edge) via the
same contract. Never carries the key character of a secret field (password timings only).
"""

from typing import Literal

from pydantic import BaseModel, Field

Channel = Literal["web", "mobile"]
Source = Literal["web_sdk", "mobile_edge"]
ActionType = Literal[
    "LOGIN", "VIEW_BALANCE", "ADD_PAYEE", "TRANSFER", "CHANGE_CONTACT", "RAISE_LIMIT"
]


class KeyEvent(BaseModel):
    key: str  # "x" placeholder for secret fields; "Backspace" tracked. NEVER the real char.
    down: float  # ms offset
    up: float  # ms offset


class DeviceInfo(BaseModel):
    fingerprint: str
    ua: str = ""
    screen: str = ""
    timezone: str = ""
    language: str = ""
    platform: str = ""  # web | android
    is_rooted: bool = False
    is_emulator: bool = False


class ActionBlock(BaseModel):
    type: ActionType = "LOGIN"


class KeystrokeBlock(BaseModel):
    events: list[KeyEvent] = Field(default_factory=list)
    field_id: str = ""


class MouseBlock(BaseModel):
    moves: list[dict] = Field(default_factory=list)  # {x, y, t}
    clicks: list[dict] = Field(default_factory=list)  # {t, dur}


class TouchBlock(BaseModel):
    swipes: list[dict] = Field(default_factory=list)  # {len, dur, vx, vy}


class ContextBlock(BaseModel):
    submitted_at: str = ""
    page: str = ""
    pre_txn_dwell_ms: float = 0.0
    session_age_s: float = 0.0
    correction_rate: float = 0.0


class BehaviorPayload(BaseModel):
    channel: Channel
    source: Source = "web_sdk"
    # Telemetry integrity binding (NFR-5)
    nonce: str
    seq: int
    ts: str  # client ISO8601 timestamp (skew-checked)
    integrity_sig: str  # HMAC-SHA256(nonce ‖ canonical(metrics) ‖ fingerprint ‖ ts)

    device: DeviceInfo
    action: ActionBlock = Field(default_factory=ActionBlock)

    # web_sdk: raw timing/motion features
    keystroke: KeystrokeBlock | None = None
    mouse: MouseBlock | None = None
    touch: TouchBlock | None = None
    # mobile_edge: pre-computed features only (raw streams stay on device)
    derived_features: dict[str, float] | None = None
    # mobile_edge: on-device LSTM Autoencoder output (Implementation.md Phase 14/18).
    # Not yet part of canonical_metrics()'s signed set -- that's Phase 17's job once the
    # Kotlin SDK exists to mirror it.
    ae_recon_error: float | None = None
    ae_model_version: str | None = None

    context: ContextBlock = Field(default_factory=ContextBlock)
