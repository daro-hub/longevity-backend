from app.domain.messages import (
    DISCLAIMER,
    GUARDRAIL_MESSAGES,
    NOT_IN_SOURCES,
    guardrail_message,
)


def test_disclaimer_has_both_locales_and_is_nonempty():
    assert DISCLAIMER["it"]
    assert DISCLAIMER["en"]


def test_not_in_sources_has_both_locales():
    assert NOT_IN_SOURCES["it"]
    assert NOT_IN_SOURCES["en"]


def test_every_guardrail_message_has_both_locales():
    for key, entry in GUARDRAIL_MESSAGES.items():
        assert entry.get("it"), f"{key} missing it"
        assert entry.get("en"), f"{key} missing en"


def test_guardrail_message_returns_localized_string():
    assert guardrail_message("guardrail.age_child", "en") == GUARDRAIL_MESSAGES["guardrail.age_child"]["en"]
    assert guardrail_message("guardrail.age_child", "it") == GUARDRAIL_MESSAGES["guardrail.age_child"]["it"]


def test_guardrail_message_unknown_key_returns_key_itself():
    assert guardrail_message("not.a.real.key", "en") == "not.a.real.key"


def test_guardrail_message_falls_back_to_it_for_unknown_locale():
    assert guardrail_message("guardrail.age_child", "fr") == GUARDRAIL_MESSAGES["guardrail.age_child"]["it"]
