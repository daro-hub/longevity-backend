"""Natural-language front-end over the scoped-editing primitives
(app.llm.scope, app.llm.planner.regenerate_scope, app.domain.substitutes).

The model's only job here is to turn free text ("scambia il pollo con
qualcosa di più leggero", "fammi un solo pasto al giorno", "cosa posso
usare al posto del salmone?") into one of a small set of STRUCTURED
operations the rest of the system already knows how to execute safely.
It never decides a macro number, same principle as everywhere else in
this codebase — it only resolves *which* deterministic/validated
mechanism to invoke and with which position(s).

Sentinel values (-1, "") stand in for "not applicable" fields rather than
Optional, because OpenAI Structured Outputs' strict mode requires every
field to be present -- true optionality isn't expressible in strict mode.
"""

from __future__ import annotations

from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.llm.scope import EditScope, ScopeError, all_positions, describe_item


class ChatOperation(str, Enum):
    REGENERATE_SCOPE = "regenerate_scope"
    REGENERATE_FULL = "regenerate_full"
    GET_ALTERNATIVES = "get_alternatives"
    CLARIFY = "clarify"


class ChatIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: ChatOperation
    scope_kind: str = Field(
        ..., description="one of plan|day|meal|item|selection -- ignored unless operation=regenerate_scope"
    )
    day_index: int = Field(..., description="-1 if not applicable")
    meal_index: int = Field(..., description="-1 if not applicable")
    item_index: int = Field(..., description="-1 if not applicable")
    selection: list[list[int]] = Field(
        ..., description="list of [day_index, meal_index, item_index] triples, only for scope_kind=selection"
    )
    target_food_key: str = Field(..., description="food_key the user is asking about -- for get_alternatives")
    instruction: str = Field(
        ..., description="the user's actual request, passed through verbatim to the executor"
    )
    clarification_question: str = Field(..., description="only used when operation=clarify")


class IntentClient(Protocol):
    def parse(self, system_prompt: str, plan_description: str, message: str, locale: str) -> ChatIntent: ...


def describe_plan(plan_dict: dict, locale: str) -> str:
    """Numbers every position so the model can resolve "il pollo" / "the
    chicken" to an exact (day, meal, item) triple instead of guessing in
    prose. Reuses app.llm.scope so this listing and the one
    regenerate_scope itself builds for the LLM never drift apart.
    """
    lines = []
    for pos in all_positions(plan_dict):
        d_idx, m_idx, i_idx = pos
        item = describe_item(plan_dict, pos)
        if locale == "en":
            lines.append(
                f"day={d_idx} meal={m_idx} item={i_idx} ({item['slot']}): "
                f"{item['food_key']} {item['grams']}g"
            )
        else:
            lines.append(
                f"giorno={d_idx} pasto={m_idx} item={i_idx} ({item['slot']}): "
                f"{item['food_key']} {item['grams']}g"
            )
    return "\n".join(lines)


def _build_intent_system_prompt(plan_description: str, locale: str) -> str:
    if locale == "en":
        return (
            "You turn a user's free-text request about their meal plan into ONE structured "
            "operation. Available operations:\n"
            "- regenerate_scope: the user wants to change specific existing item(s) (swap one "
            "ingredient, redo one meal, redo one day, or an arbitrary selection). Resolve exactly "
            "which position(s) they mean using the plan listing below, and set scope_kind + indices "
            "accordingly. Put the user's actual request in `instruction` (e.g. 'something with less fat').\n"
            "- regenerate_full: the user wants to change the overall STRUCTURE of the plan itself "
            "(e.g. 'only one meal a day', 'add a 6th day', 'make it vegetarian overall'), not just "
            "swap specific foods. Put their request in `instruction`.\n"
            "- get_alternatives: the user is asking what else they could use instead of ONE food, "
            "without committing to a change yet. Set target_food_key to that food's exact key.\n"
            "- clarify: the request is ambiguous (e.g. you can't tell which item they mean) -- ask a "
            "short clarifying question in `clarification_question`.\n\n"
            f"Current plan (day/meal/item indices are 0-based):\n{plan_description}\n\n"
            "Use indices from this exact listing -- never invent a position that isn't in it. "
            "Leave inapplicable fields at their sentinel value (-1 for indices, empty string/list "
            "for the rest)."
        )
    return (
        "Trasformi la richiesta in linguaggio naturale dell'utente sul suo piano alimentare in UNA "
        "operazione strutturata. Operazioni disponibili:\n"
        "- regenerate_scope: l'utente vuole cambiare uno o più elementi esistenti specifici "
        "(scambiare un ingrediente, rifare un pasto, rifare un giorno, o una selezione arbitraria). "
        "Risolvi esattamente a quale posizione/i si riferisce usando l'elenco del piano sotto, e "
        "imposta scope_kind + indici di conseguenza. Metti la richiesta reale dell'utente in "
        "`instruction` (es. 'qualcosa con meno grassi').\n"
        "- regenerate_full: l'utente vuole cambiare la STRUTTURA generale del piano stesso (es. "
        "'solo un pasto al giorno', 'aggiungi un sesto giorno', 'rendilo vegetariano in generale'), "
        "non solo scambiare alimenti specifici. Metti la richiesta in `instruction`.\n"
        "- get_alternatives: l'utente chiede cosa potrebbe usare al posto di UN alimento, senza "
        "ancora impegnarsi a un cambio. Imposta target_food_key con la chiave esatta di quell'alimento.\n"
        "- clarify: la richiesta è ambigua (es. non capisci a quale elemento si riferisce) -- fai "
        "una breve domanda di chiarimento in `clarification_question`.\n\n"
        f"Piano attuale (gli indici giorno/pasto/item partono da 0):\n{plan_description}\n\n"
        "Usa indici solo da questo elenco esatto -- non inventare mai una posizione che non c'è. "
        "Lascia i campi non applicabili al loro valore sentinella (-1 per gli indici, stringa/lista "
        "vuota per gli altri)."
    )


def resolve_intent(client: IntentClient, plan_dict: dict, message: str, locale: str) -> ChatIntent:
    plan_description = describe_plan(plan_dict, locale)
    system_prompt = _build_intent_system_prompt(plan_description, locale)
    return client.parse(system_prompt, plan_description, message, locale)


class ScopeConversionError(ScopeError):
    pass


def intent_to_edit_scope(intent: ChatIntent) -> EditScope:
    if intent.scope_kind == "plan":
        return EditScope(kind="plan")
    if intent.scope_kind == "day":
        return EditScope(kind="day", day_index=intent.day_index)
    if intent.scope_kind == "meal":
        return EditScope(kind="meal", day_index=intent.day_index, meal_index=intent.meal_index)
    if intent.scope_kind == "item":
        return EditScope(
            kind="item",
            day_index=intent.day_index,
            meal_index=intent.meal_index,
            item_index=intent.item_index,
        )
    if intent.scope_kind == "selection":
        positions = tuple(tuple(p) for p in intent.selection)
        return EditScope(kind="selection", positions=positions)
    raise ScopeConversionError(f"unknown scope_kind from model: {intent.scope_kind!r}")
