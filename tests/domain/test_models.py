from app.domain.models import TargetsResult


def test_targets_result_refused_property():
    result = TargetsResult(targets=None, violations=())
    assert result.refused is True
    assert result.plan_allowed is False


def test_targets_result_plan_allowed_when_targets_present(monkeypatch):
    # A minimal stand-in is enough; plan_allowed only checks refused.
    result = TargetsResult(targets=object(), violations=())
    assert result.refused is False
    assert result.plan_allowed is True
