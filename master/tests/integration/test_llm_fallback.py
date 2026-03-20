import pytest

from master.adapters.llm_strategy import LLMStrategy
from master.domain.board import Board
from master.domain.models import Emotion


class TestLLMParsing:
    def test_parse_valid_response(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        decision = LLMStrategy._parse_response(
            {"next_move": 4, "emotion": "joy", "dialogue": "ここだ！"}, board,
        )
        assert decision.next_move == 4
        assert decision.emotion == Emotion.JOY
        assert decision.dialogue == "ここだ！"

    def test_parse_occupied_cell_raises(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        with pytest.raises(Exception):
            LLMStrategy._parse_response(
                {"next_move": 0, "emotion": "joy", "dialogue": "t"}, board,
            )

    def test_parse_out_of_range_raises(self):
        board = Board.initial()
        with pytest.raises(Exception):
            LLMStrategy._parse_response(
                {"next_move": 9, "emotion": "joy", "dialogue": "t"}, board,
            )


class TestLLMFallback:
    def test_fallback_returns_valid_move(self):
        board = Board.from_list([1, 2, 1, 2, 0, 0, 0, 0, 0])
        decision = LLMStrategy._fallback(board)
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.NEUTRAL
        assert decision.dialogue != ""

    def test_fallback_unknown_emotion_defaults(self):
        board = Board.initial()
        decision = LLMStrategy._parse_response(
            {"next_move": 0, "emotion": "unknown_emotion", "dialogue": "t"},
            board,
        )
        assert decision.emotion == Emotion.NEUTRAL
