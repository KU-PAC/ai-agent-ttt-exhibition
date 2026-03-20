from __future__ import annotations

import asyncio

from openai import AsyncOpenAI

from master.application.ports import LLMClientPort


class OpenAILLMClient(LLMClientPort):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def chat(
        self, system: str, user_message: str, timeout: float = 10.0,
    ) -> str:
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=0.8,
            ),
            timeout=timeout,
        )
        return response.choices[0].message.content or "{}"
