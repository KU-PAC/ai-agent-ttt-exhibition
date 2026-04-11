from enum import Enum


class GamePhase(Enum):
    STANDBY = "standby"
    HUMAN_TURN = "human_turn"
    AI_THINKING = "ai_thinking"
    GAME_OVER = "game_over"
    RESETTING = "resetting"
