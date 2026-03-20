from master.domain.board import Board


class TestBoard:
    def test_initial_board_is_all_zeros(self):
        board = Board.initial()
        assert board.to_list() == [0] * 9

    def test_set_returns_new_board(self):
        board = Board.initial()
        new_board = board.set(4, 1)
        assert board.get(4) == 0
        assert new_board.get(4) == 1

    def test_from_list(self):
        cells = [1, 0, 2, 0, 1, 0, 0, 0, 0]
        board = Board.from_list(cells)
        assert board.to_list() == cells

    def test_empty_cells(self):
        board = Board.from_list([1, 0, 2, 0, 1, 0, 0, 0, 0])
        assert board.empty_cells() == [1, 3, 5, 6, 7, 8]

    def test_empty_cells_full_board(self):
        board = Board.from_list([1, 2, 1, 2, 1, 2, 1, 2, 1])
        assert board.empty_cells() == []

    def test_frozen(self):
        board = Board.initial()
        try:
            board.cells = (1, 2, 3)
            assert False, "Should raise"
        except AttributeError:
            pass

    def test_equality(self):
        a = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        b = Board.from_list([1, 0, 0, 0, 0, 0, 0, 0, 0])
        assert a == b

    def test_set_out_of_range_raises(self):
        board = Board.initial()
        try:
            board.set(9, 1)
            assert False, "Should raise"
        except IndexError:
            pass
