"""Real OpenAI-backed implementation of app.llm.intent.IntentClient.

Same Structured Outputs approach as app.llm.openai_client: strict schema,
low temperature (this is a classification task, not creative writing).
"""

from __future__ import annotations

import json

from app.llm.intent import ChatIntent

MODEL = "gpt-4o-mini"
TEMPERATURE = 0.0


class OpenAIIntentClient:
    def __init__(self, client, model: str = MODEL):
        self._client = client
        self._model = model

    def parse(self, system_prompt: str, plan_description: str, message: str, locale: str) -> ChatIntent:
        completion = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=TEMPERATURE,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "chat_intent",
                    "strict": True,
                    "schema": ChatIntent.model_json_schema(),
                },
            },
        )
        content = completion.choices[0].message.content
        if not content:
            raise ValueError("empty completion from model")
        return ChatIntent.model_validate(json.loads(content))
