class MasterError(Exception):
    pass


class InvalidGameStateError(MasterError):
    pass


class PlacementError(MasterError):
    pass
