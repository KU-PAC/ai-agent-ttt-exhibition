from master.domain.board import Board
from master.domain.game_rule import (
    check_winner,
    find_human_move,
    is_valid_ai_move,
    judge,
)
from master.domain.models import GameResult


class TestJudge:
    def test_ongoing(self):
        board = Board.initial()
        assert judge(board) == GameResult.ONGOING

    def test_human_wins_row(self):
        board = Board.from_list([1, 1, 1, 0, 0, 0, 0, 0, 0])
        assert judge(board) == GameResult.WIN_HUMAN

    def test_ai_wins_column(self):
        board = Board.from_list([2, 0, 0, 2, 0, 0, 2, 0, 0])
        assert judge(board) == GameResult.WIN_AI

    def test_ai_wins_diagonal(self):
        board = Board.from_list([2, 0, 0, 0, 2, 0, 0, 0, 2])
        assert judge(board) == GameResult.WIN_AI

    def test_draw(self):
        board = Board.from_list([1, 2, 1, 1, 2, 2, 2, 1, 1])
        assert judge(board) == GameResult.DRAW


class TestCheckWinner:
    def test_no_winner(self):
        assert check_winner(Board.initial()) is None

    def test_human_wins(self):
        board = Board.from_list([0, 0, 0, 1, 1, 1, 0, 0, 0])
        assert check_winner(board) == 1

    def test_ai_wins_anti_diagonal(self):
        board = Board.from_list([0, 0, 2, 0, 2, 0, 2, 0, 0])
        assert check_winner(board) == 2


class TestHumanMoveValidation:
    def test_valid_single_move(self):
        current = Board.from_list([0, 0, 0, 0, 0, 0, 0, 0, 0])
        new = Board.from_list([0, 0, 0, 0, 1, 0, 0, 0, 0])
        assert find_human_move(current, new) == 4

    def test_two_cells_changed_is_invalid(self):
        current = Board.initial()
        new = Board.from_list([1, 1, 0, 0, 0, 0, 0, 0, 0])
        assert find_human_move(current, new) is None

    def test_ai_piece_placed_is_invalid(self):
        current = Board.initial()
        new = Board.from_list([2, 0, 0, 0, 0, 0, 0, 0, 0])
        assert find_human_move(current, new) is None

    def test_overwrite_existing_piece_is_invalid(self):
        current = Board.from_list([2, 0, 0, 0, 0, 0, 0, 0, 0])
        new = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        assert find_human_move(current, new) is None

    def test_no_change_is_invalid(self):
        board = Board.initial()
        assert find_human_move(board, board) is None


class TestAIMoveValidation:
    def test_valid_move(self):
        board = Board.initial()
        assert is_valid_ai_move(board, 0) is True

    def test_occupied_cell(self):
        board = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        assert is_valid_ai_move(board, 0) is False

    def test_out_of_range(self):
        board = Board.initial()
        assert is_valid_ai_move(board, 9) is False
        assert is_valid_ai_move(board, -1) is False
