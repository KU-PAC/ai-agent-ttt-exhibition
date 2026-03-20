import json

import pytest

from master.adapters.algorithm_strategy import AlgorithmStrategy
from master.adapters.llm_reaction_adapter import LLMReactionAdapter
from master.adapters.llm_strategy import LLMStrategy
from master.domain.board import Board
from master.domain.models import Emotion, Reaction
from tests.mocks.mock_llm import MockLLMClient, MockReactionGenerator


class TestLLMParsing:
    def test_parse_valid_response(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        decision = LLMStrategy._parse_response(
            {"next_move": 4, "emotion": "joy", "dialogue": "ここだ！"},
            board,
        )
        assert decision.next_move == 4
        assert decision.emotion == Emotion.JOY
        assert decision.dialogue == "ここだ！"

    def test_parse_occupied_cell_raises(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        with pytest.raises(Exception):
            LLMStrategy._parse_response(
                {"next_move": 0, "emotion": "joy", "dialogue": "t"},
                board,
            )

    def test_parse_out_of_range_raises(self):
        board = Board.initial()
        with pytest.raises(Exception):
            LLMStrategy._parse_response(
                {"next_move": 9, "emotion": "joy", "dialogue": "t"},
                board,
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


class TestLLMRetryLoop:
    @pytest.mark.asyncio
    async def test_retry_on_occupied_cell(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        llm = MockLLMClient(
            responses=[
                json.dumps({"next_move": 0, "emotion": "joy", "dialogue": "a"}),
                json.dumps({"next_move": 4, "emotion": "joy", "dialogue": "b"}),
            ]
        )
        strategy = LLMStrategy(llm_client=llm, max_retries=3, timeout=5.0)
        decision = await strategy.decide(board, [])
        assert decision.next_move == 4
        assert llm.call_count == 2

    @pytest.mark.asyncio
    async def test_fallback_after_3_failures(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        llm = MockLLMClient(
            responses=[
                json.dumps({"next_move": 0, "emotion": "joy", "dialogue": "a"}),
                json.dumps({"next_move": 0, "emotion": "joy", "dialogue": "b"}),
                json.dumps({"next_move": 0, "emotion": "joy", "dialogue": "c"}),
            ]
        )
        strategy = LLMStrategy(llm_client=llm, max_retries=3, timeout=5.0)
        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.NEUTRAL
        assert llm.call_count == 3

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        board = Board.initial()
        llm = MockLLMClient(
            responses=[
                "not json",
                "also not json",
                "still not json",
            ]
        )
        strategy = LLMStrategy(llm_client=llm, max_retries=3, timeout=5.0)
        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.NEUTRAL

    @pytest.mark.asyncio
    async def test_fallback_game_continues(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        llm = MockLLMClient(
            responses=[
                "bad",
                "bad",
                "bad",
            ]
        )
        strategy = LLMStrategy(llm_client=llm, max_retries=3, timeout=5.0)
        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.NEUTRAL
        assert llm.call_count == 3


class TestAlgorithmStrategyIntegration:
    @pytest.mark.asyncio
    async def test_algorithm_with_mock_reaction(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        reaction = Reaction(emotion=Emotion.FUN, dialogue="テスト")
        reaction_gen = MockReactionGenerator(reaction=reaction)
        strategy = AlgorithmStrategy(reaction_generator=reaction_gen)

        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.FUN
        assert decision.dialogue == "テスト"

    @pytest.mark.asyncio
    async def test_algorithm_fallback_on_reaction_failure(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])

        class FailingReactionGen(MockReactionGenerator):
            async def generate(self, board, position, move_history):
                raise RuntimeError("LLM down")

        strategy = AlgorithmStrategy(reaction_generator=FailingReactionGen())
        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.NEUTRAL

    @pytest.mark.asyncio
    async def test_algorithm_with_llm_client(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        llm = MockLLMClient(
            responses=[
                json.dumps({"emotion": "angry", "dialogue": "くっ"}),
            ]
        )
        reaction_gen = LLMReactionAdapter(
            llm_client=llm,
            max_retries=1,
            timeout=5.0,
        )
        strategy = AlgorithmStrategy(reaction_generator=reaction_gen)

        decision = await strategy.decide(board, [])
        assert decision.next_move in board.empty_cells()
        assert decision.emotion == Emotion.ANGRY
        assert decision.dialogue == "くっ"
