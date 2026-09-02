from app.api import require_proxy_key


def test_proxy_key_rejects_empty_or_oversized_credentials():
    for value in ("", "x" * 513):
        try:
            require_proxy_key(f"Bearer {value}")
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 401
        else:
            raise AssertionError("invalid credential was accepted")
