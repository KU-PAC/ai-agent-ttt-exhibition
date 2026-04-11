from __future__ import annotations

import asyncio

from anthropic import AsyncAnthropic
from openai import AsyncOpenAI

from master.application.ports import LLMClientPort


class AnthropicLLMClient(LLMClientPort):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-haiku-4-5-20251001",
        max_tokens: int = 256,
    ) -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def chat(
        self,
        system: str,
        user_message: str,
        timeout: float = 10.0,
    ) -> str:
        response = await asyncio.wait_for(
            self._client.messages.create(
                model=self._model,
                max_tokens=self._max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            ),
            timeout=timeout,
        )
        return response.content[0].text


class OpenAILLMClient(LLMClientPort):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 256,
        temperature: float = 0.8,
    ) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature

    async def chat(
        self,
        system: str,
        user_message: str,
        timeout: float = 10.0,
    ) -> str:
        response = await asyncio.wait_for(
            self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                response_format={"type": "json_object"},
                temperature=self._temperature,
            ),
            timeout=timeout,
        )
        return response.choices[0].message.content or "{}"
