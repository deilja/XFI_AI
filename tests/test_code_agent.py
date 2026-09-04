import pytest

from app.code_agent import _json, _safe_path


def test_safe_path_allows_normal_source_file():
    assert _safe_path("bot/handlers/ai.py") is True


@pytest.mark.parametrize(
    "path",
    ["/etc/passwd", "../secret.py", ".env", "config/credentials.json", "keys/private_key.pem"],
)
def test_safe_path_blocks_sensitive_paths(path):
    assert _safe_path(path) is False


def test_json_accepts_markdown_fenced_json():
    assert _json("```json\n{\"ready\": true}\n```") == {"ready": True}


def test_json_rejects_non_object():
    with pytest.raises(TypeError):
        _json("[1, 2, 3]")
