from master.domain.errors import MasterError


class VisionTimeoutError(MasterError):
    pass


class RobotTimeoutError(MasterError):
    pass


class LLMInvalidResponseError(MasterError):
    pass


class ReactionGenerationError(MasterError):
    pass
