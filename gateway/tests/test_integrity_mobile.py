"""Phase 17 acceptance check (Implementation.md lines 791-813): the two new
mobile_edge signed fields (`ae_recon_error`, `ae_model_version`) canonicalize and sign
byte-for-byte against the shared golden vector also asserted by
`behavior-sdk/src/payload.test.ts` (TypeScript) and Phase 18's Android
CanonicalTest/SignerTest (Kotlin)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import settings
from app.schemas.behavior import BehaviorPayload
from app.services import integrity

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "golden_canonical_mobile.json"


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


@pytest.fixture(scope="module")
def golden_payload(golden: dict) -> BehaviorPayload:
    return BehaviorPayload(**golden["payload"], integrity_sig="placeholder")


def test_jwt_secret_matches_the_golden_vectors_signing_secret(golden: dict):
    # The fixture is only a valid cross-language pin if every implementation signs
    # with the same secret it was generated against.
    assert settings.jwt_secret == golden["secret"]


def test_canonical_metrics_matches_the_golden_vector_exactly(
    golden: dict, golden_payload: BehaviorPayload
):
    assert integrity.canonical_metrics(golden_payload) == golden["canonical"]


def test_signature_matches_the_golden_vector_exactly(golden: dict, golden_payload: BehaviorPayload):
    assert integrity.compute_signature(golden_payload) == golden["integrity_sig"]


def test_changing_ae_recon_error_changes_the_signature(golden_payload: BehaviorPayload):
    tampered = golden_payload.model_copy(update={"ae_recon_error": 0.9})
    assert integrity.compute_signature(tampered) != integrity.compute_signature(golden_payload)


def test_changing_ae_model_version_changes_the_signature(golden_payload: BehaviorPayload):
    tampered = golden_payload.model_copy(update={"ae_model_version": "lstm_autoencoder@2099-01-01"})
    assert integrity.compute_signature(tampered) != integrity.compute_signature(golden_payload)
