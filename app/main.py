from .config import get_settings
from .models import AnalysisRequest, AnalysisResult


def analyze(request: AnalysisRequest) -> AnalysisResult:
    text = request.text.strip()
    if not text:
        return AnalysisResult(status="invalid", summary="Пустой входной текст")

    return AnalysisResult(
        status="accepted",
        summary="Данные приняты для AI-анализа",
    )


def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": settings.app_name}
