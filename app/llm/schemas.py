"""The LLM's meal-plan output schema.

The decisive design choice is what's NOT here: no `calories`, no
`protein_g`, no macro field of any kind, at any level. If the field
doesn't exist, the model cannot hallucinate it, and there is nothing
tempting to trust. Every total in the system is computed by
app.domain.nutrition from these food_key/grams pairs — see that module's
docstring.

Used with OpenAI's Structured Outputs (`response_format: json_schema`,
`strict: true`), which requires every field to be required and
`additionalProperties: false` at every level — `model_config` below
enforces the second half; being non-Optional enforces the first.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class MealSlot(str, Enum):
    BREAKFAST = "breakfast"
    MORNING_SNACK = "morning_snack"
    LUNCH = "lunch"
    AFTERNOON_SNACK = "afternoon_snack"
    DINNER = "dinner"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanItemDraft(StrictModel):
    food_key: str = Field(..., description="Must be one of the food_key values supplied in the catalogue")
    grams: float = Field(..., gt=0)
    note: str = Field(..., description="Short prep note, or empty string")


class MealDraft(StrictModel):
    slot: MealSlot
    items: list[PlanItemDraft]


class DayDraft(StrictModel):
    meals: list[MealDraft]


class MealPlanDraft(StrictModel):
    days: list[DayDraft]

    def to_plain_dict(self) -> dict:
        return self.model_dump(mode="json")
