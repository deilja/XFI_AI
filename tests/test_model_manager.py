from app.model_manager import ModelManager, ModelProfile


def test_candidates_are_capability_aware_and_weighted():
    manager = ModelManager(
        (
            ModelProfile("a", "m-a", ("ai", "code-agent"), 50),
            ModelProfile("b", "m-b", ("ai",), 90),
        )
    )
    assert [p.model for p in manager.candidates("ai")] == ["m-b", "m-a"]
    assert [p.model for p in manager.candidates("code-agent")] == ["m-a"]


def test_failed_model_enters_cooldown_and_is_skipped():
    manager = ModelManager((ModelProfile("a", "m-a", ("ai",), 100),))
    profile = manager.profiles[0]
    manager.record(profile, False, 0.5, 429)
    assert manager.candidates("ai") == []


def test_success_reduces_failures_and_restores_model():
    manager = ModelManager((ModelProfile("a", "m-a", ("ai",), 100),))
    profile = manager.profiles[0]
    manager.record(profile, False, 0.5, 500)
    manager.record(profile, True, 0.2, 200)
    assert manager.candidates("ai")[0].model == "m-a"
