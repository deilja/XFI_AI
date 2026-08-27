from app.main import analyze, health
from app.models import AnalysisRequest


def test_health():
    assert health()["status"] == "ok"


def test_empty_input():
    result = analyze(AnalysisRequest(text=""))
    assert result.status == "invalid"


def test_analysis_accepts_text():
    result = analyze(AnalysisRequest(text="xray connection error"))
    assert result.status == "accepted"
