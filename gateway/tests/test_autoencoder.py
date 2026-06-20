"""Phase 13 acceptance check (Implementation.md lines 689-695): the LSTM Autoencoder
scoring module (pure, injected-model, mirrors `isolation_forest.py`'s shape) plus the
registry's new per-model_name artifact loader (joblib vs. onnx). No live infra: the
ONNX session and the Postgres `model_registry` row are both stubs.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.scoring import registry as registry_module
from app.scoring.autoencoder import N_FEATURES, SEQ_LEN, behavior_score, reconstruction_error
from app.scoring.calibration import CalibrationParams

_ZERO_SEQUENCE = np.zeros((SEQ_LEN, N_FEATURES), dtype=np.float32)


class _StubInput:
    name = "input"


class _StubSession:
    """Duck-types `onnxruntime.InferenceSession`: `get_inputs()` + `run()`. Returns a
    caller-supplied reconstruction regardless of the actual input, so each test controls
    exactly what the "model" reconstructs."""

    def __init__(self, reconstruction: np.ndarray):
        self._reconstruction = reconstruction

    def get_inputs(self):
        return [_StubInput()]

    def run(self, output_names, inputs):
        assert output_names is None
        assert "input" in inputs
        assert inputs["input"].shape == (1, SEQ_LEN, N_FEATURES)
        return [self._reconstruction]


def test_reconstruction_error_is_zero_for_perfect_reconstruction():
    model = _StubSession(_ZERO_SEQUENCE.reshape(1, SEQ_LEN, N_FEATURES))
    assert reconstruction_error(_ZERO_SEQUENCE, model=model) == pytest.approx(0.0)


def test_reconstruction_error_equals_squared_offset_for_constant_diff():
    offset = 3.0
    recon = (_ZERO_SEQUENCE + offset).reshape(1, SEQ_LEN, N_FEATURES)
    model = _StubSession(recon)
    err = reconstruction_error(_ZERO_SEQUENCE, model=model)
    assert err == pytest.approx(offset**2)


def test_reconstruction_error_ignores_padded_rows_under_mask():
    """A short window padded with zeros, but the autoencoder's stub reconstruction
    disagrees wildly on the padded rows -- the mask must exclude them entirely, so the
    error reflects only the one real row (a perfect match -> 0), not the padding noise."""
    recon = _ZERO_SEQUENCE.copy()
    recon[1:] = 100.0  # garbage on every row except the first
    model = _StubSession(recon.reshape(1, SEQ_LEN, N_FEATURES))
    mask = [True] + [False] * (SEQ_LEN - 1)

    err = reconstruction_error(_ZERO_SEQUENCE, model=model, mask=mask)
    assert err == pytest.approx(0.0)


def test_reconstruction_error_all_masked_out_returns_zero_not_nan():
    model = _StubSession(_ZERO_SEQUENCE.reshape(1, SEQ_LEN, N_FEATURES))
    err = reconstruction_error(_ZERO_SEQUENCE, model=model, mask=[False] * SEQ_LEN)
    assert err == 0.0


def test_behavior_score_runs_reconstruction_error_through_calibration():
    offset = 3.0
    recon = (_ZERO_SEQUENCE + offset).reshape(1, SEQ_LEN, N_FEATURES)
    model = _StubSession(recon)
    params = CalibrationParams(scale=2.0, threshold=offset**2, temperature=1.0)

    score = behavior_score(_ZERO_SEQUENCE, model=model, calib_params=params)
    assert score == pytest.approx(0.5, abs=1e-9)  # recon error lands exactly on threshold
    assert 0.0 <= score <= 1.0


# --- registry: lstm_autoencoder resolves via onnxruntime; isolation_forest/xgboost_txn
# still resolve via joblib (Implementation.md Phase 13's registry.py edit) ---------------


class _FakeRow:
    def __init__(self, version: str = "v1", artifact_uri: str = "s3://cogniguard/m/v1/model"):
        self.version = version
        self.artifact_uri = artifact_uri
        self.deployed_at = None


class _FakeSession:
    def __init__(self, row: _FakeRow | None):
        self._row = row

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def scalar(self, _stmt):
        return self._row


@pytest.fixture
def fake_loaders(monkeypatch):
    """Stub Postgres (row lookup), the local-artifact existence check (skip S3
    download), and both loader callables -- isolates `_load`'s model_name -> (filename,
    loader) dispatch from real infra entirely."""
    row = _FakeRow()
    monkeypatch.setattr(registry_module, "SessionLocal", lambda: _FakeSession(row))
    monkeypatch.setattr(registry_module.os.path, "exists", lambda path: True)

    calls: list[tuple[str, str]] = []

    def _fake_joblib_load(path: str) -> str:
        calls.append(("joblib", path))
        return "joblib-model"

    def _fake_onnx_session(path: str) -> str:
        calls.append(("onnx", path))
        return "onnx-session"

    monkeypatch.setattr(
        registry_module,
        "_ARTIFACT_SPECS",
        {
            "isolation_forest": ("model.joblib", _fake_joblib_load),
            "xgboost_txn": ("model.joblib", _fake_joblib_load),
            "lstm_autoencoder": ("model.onnx", _fake_onnx_session),
        },
    )
    return calls


def test_registry_resolves_lstm_autoencoder_via_onnx_loader(fake_loaders):
    loaded = registry_module.Registry().get("lstm_autoencoder")
    assert loaded.model == "onnx-session"
    assert len(fake_loaders) == 1
    assert fake_loaders[0][0] == "onnx"
    assert fake_loaders[0][1].endswith("model.onnx")


@pytest.mark.parametrize("model_name", ["isolation_forest", "xgboost_txn"])
def test_registry_still_resolves_existing_models_via_joblib(fake_loaders, model_name):
    loaded = registry_module.Registry().get(model_name)
    assert loaded.model == "joblib-model"
    assert len(fake_loaders) == 1
    assert fake_loaders[0][0] == "joblib"
    assert fake_loaders[0][1].endswith("model.joblib")
