from master.domain.board import Board
from master.domain.entertaining_ai import (
    MoveQuality,
    estimate_skill,
    evaluate_human_move,
    select_move,
)
from master.domain.game_rule import check_winner
from master.domain.models import Move


class TestEvaluateHumanMove:
    def test_optimal_move(self):
        board = Board.from_list([1, 0, 0, 0, 2, 0, 0, 0, 0])
        quality = evaluate_human_move(board, 2)
        assert quality in (MoveQuality.OPTIMAL, MoveQuality.GOOD)

    def test_blunder_gives_ai_win(self):
        board = Board.from_list([2, 2, 0, 1, 0, 0, 0, 0, 0])
        quality = evaluate_human_move(board, 8)
        assert quality == MoveQuality.BLUNDER


class TestEstimateSkill:
    def test_no_moves_returns_half(self):
        assert estimate_skill([], []) == 0.5

    def test_all_optimal_returns_high(self):
        boards = [Board.initial()]
        moves = [Move(player=1, position=4)]  # center is typically optimal/good
        skill = estimate_skill(moves, boards)
        assert skill >= 0.7


class TestSelectMove:
    def test_takes_winning_move(self):
        board = Board.from_list([2, 2, 0, 1, 1, 0, 0, 0, 0])
        pos = select_move(board, [], [])
        assert pos == 2
        assert check_winner(board.set(pos, 2)) == 2

    def test_blocks_human_win(self):
        board = Board.from_list([1, 1, 0, 2, 0, 0, 0, 0, 0])
        pos = select_move(board, [], [])
        assert pos == 2

    def test_returns_valid_position(self):
        board = Board.from_list([1, 2, 1, 2, 1, 0, 0, 0, 2])
        pos = select_move(board, [], [])
        assert pos in board.empty_cells()
