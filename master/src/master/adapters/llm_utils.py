from __future__ import annotations

import re

from master.domain.models import Emotion

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)

EMOTION_MAP: dict[str, Emotion] = {e.value: e for e in Emotion}


def extract_json(text: str) -> str:
    m = _CODE_BLOCK_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def parse_emotion(raw: str) -> Emotion:
    return EMOTION_MAP.get(raw.lower(), Emotion.NEUTRAL)
