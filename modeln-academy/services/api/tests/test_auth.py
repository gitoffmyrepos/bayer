from datetime import UTC, datetime, timedelta

from services.api.app.auth import hash_password, verify_password


def test_passwords_use_argon2_and_verify_without_plaintext_storage() -> None:
    encoded = hash_password("correct horse battery staple")

    assert encoded.startswith("$argon2")
    assert "correct horse battery staple" not in encoded
    assert verify_password(encoded, "correct horse battery staple") is True
    assert verify_password(encoded, "wrong password") is False


def test_expiry_comparison_uses_utc() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)

    assert now < now + timedelta(hours=1)
