__all__ = [
    "MasterError",
    "VisionTimeoutError",
    "RobotTimeoutError",
    "PlacementError",
    "LLMTimeoutError",
    "LLMInvalidResponseError",
    "ReactionGenerationError",
    "InvalidGameStateError",
]


class MasterError(Exception):
    pass


class VisionTimeoutError(MasterError):
    pass


class RobotTimeoutError(MasterError):
    pass


class PlacementError(MasterError):
    pass


class LLMTimeoutError(MasterError):
    pass


class LLMInvalidResponseError(MasterError):
    pass


class ReactionGenerationError(MasterError):
    pass


class InvalidGameStateError(MasterError):
    pass
