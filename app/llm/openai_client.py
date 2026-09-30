"""The real OpenAI-backed implementation of app.llm.planner.LLMPlanClient.

Uses Structured Outputs (`response_format: json_schema`, `strict: true`)
generated from the pydantic schema itself — not "please reply with JSON".
temperature is low (0.2, vs. the 0.7 the old /ask endpoint uses) because
this is a structured-choice task, not open-ended prose; a wandering
temperature is a large part of why unconstrained generation drifts off
the schema's intent.
"""

from __future__ import annotations

import json

from app.llm.schemas import MealPlanDraft

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.2


class OpenAIPlanClient:
    def __init__(self, client, model: str = MODEL):
        self._client = client
        self._model = model

    def _complete(self, messages: list[dict]) -> MealPlanDraft:
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=TEMPERATURE,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "meal_plan_draft",
                    "strict": True,
                    "schema": MealPlanDraft.model_json_schema(),
                },
            },
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("empty completion from model")
        return MealPlanDraft.model_validate(json.loads(content))

    def create_plan(self, system_prompt: str, catalogue: list[dict], locale: str) -> MealPlanDraft:
        catalogue_json = json.dumps(catalogue, ensure_ascii=False)
        return self._complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Catalogo alimenti disponibili:\n{catalogue_json}"},
            ]
        )

    def repair_plan(
        self,
        system_prompt: str,
        catalogue: list[dict],
        previous_draft: MealPlanDraft,
        repair_note: str,
        locale: str,
    ) -> MealPlanDraft:
        catalogue_json = json.dumps(catalogue, ensure_ascii=False)
        return self._complete(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Catalogo alimenti disponibili:\n{catalogue_json}"},
                {"role": "assistant", "content": previous_draft.model_dump_json()},
                {"role": "user", "content": repair_note},
            ]
        )
