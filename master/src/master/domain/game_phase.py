from enum import Enum

__all__ = ["GamePhase"]


class GamePhase(Enum):
    STANDBY = "standby"
    HUMAN_TURN = "human_turn"
    AI_THINKING = "ai_thinking"
    AI_PLACING = "ai_placing"
    AI_VERIFYING = "ai_verifying"
    GAME_OVER = "game_over"
    RESETTING = "resetting"
