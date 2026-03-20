from master.domain.board import Board
from master.domain.minimax import minimax, score_all_moves


class TestMinimax:
    def test_ai_winning_board(self):
        board = Board.from_list([2, 2, 0, 1, 1, 0, 0, 0, 0])
        score = minimax(board, 2, depth=0)
        assert score > 0

    def test_human_winning_board(self):
        board = Board.from_list([1, 1, 0, 2, 2, 0, 0, 0, 0])
        score = minimax(board, 1, depth=0)
        assert score < 0

    def test_empty_board_is_draw(self):
        board = Board.initial()
        score = minimax(board, 2, depth=0)
        assert score == 0

    def test_draw_position(self):
        board = Board.from_list([1, 2, 1, 2, 1, 0, 2, 1, 2])
        score = minimax(board, 1, depth=0)
        assert score == 0


class TestScoreAllMoves:
    def test_returns_all_empty_cells(self):
        board = Board.from_list([1, 0, 0, 0, 2, 0, 0, 0, 0])
        moves = score_all_moves(board, 2)
        positions = {m.position for m in moves}
        assert positions == {1, 2, 3, 5, 6, 7, 8}

    def test_winning_move_flagged(self):
        board = Board.from_list([2, 2, 0, 1, 1, 0, 0, 0, 0])
        moves = score_all_moves(board, 2)
        winning = [m for m in moves if m.is_winning]
        assert len(winning) == 1
        assert winning[0].position == 2

    def test_blocking_move_flagged(self):
        board = Board.from_list([1, 1, 0, 2, 0, 0, 0, 0, 0])
        moves = score_all_moves(board, 2)
        blocking = [m for m in moves if m.is_blocking]
        assert any(m.position == 2 for m in blocking)

    def test_sorted_descending_for_ai(self):
        board = Board.initial()
        moves = score_all_moves(board, 2)
        scores = [m.score for m in moves]
        assert scores == sorted(scores, reverse=True)
