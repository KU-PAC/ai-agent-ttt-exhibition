from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum


class Emotion(Enum):
    NORMAL = "normal"
    HAPPY = "happy"
    ANGRY = "angry"
    SAD = "sad"
    SURPRISED = "surprised"
    SHY = "shy"
    EXCITED = "excited"
    SMUG = "smug"
    CALM = "calm"


class GameResult(Enum):
    ONGOING = "ongoing"
    WIN_HUMAN = "win_human"
    WIN_AI = "win_ai"
    DRAW = "draw"


@dataclass(frozen=True)
class AIDecision:
    next_move: int
    emotion: Emotion
    dialogue: str


@dataclass(frozen=True)
class Reaction:
    emotion: Emotion
    dialogue: str


@dataclass(frozen=True)
class PlacementResult:
    success: bool
    position: int
    error_detail: str | None


@dataclass(frozen=True)
class Move:
    player: int  # 1=human, 2=AI
    position: int  # 0~8


FALLBACK_EMOTION: Emotion = Emotion.NORMAL

FALLBACK_DIALOGUES: list[str] = [
    "なるほど、ではこちらにしましょう",
    "うーん、ここかな",
    "よし、決めました",
]


def make_fallback_reaction() -> Reaction:
    return Reaction(
        emotion=FALLBACK_EMOTION,
        dialogue=random.choice(FALLBACK_DIALOGUES),
    )
