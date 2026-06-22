"""PII masking for customer-facing read endpoints (Phase 28) -- raw account numbers,
emails, and phone numbers are never returned to the client; only enough is kept visible
for a customer to recognize their own record."""

from __future__ import annotations


def mask_account_number(value: str | None) -> str | None:
    if not value:
        return value
    tail = value[-4:]
    return f"{'X' * max(len(value) - 4, 0)}{tail}"


def mask_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, domain = value.split("@", 1)
    visible = local[:1] or "*"
    return f"{visible}{'*' * max(len(local) - 1, 1)}@{domain}"


def mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    tail = value[-4:]
    return f"{'X' * max(len(value) - 4, 0)}{tail}"
