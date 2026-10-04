class AutomationAlreadyRunningError(Exception):
    def __init__(self, message: str = "An automation run is already in progress."):
        super().__init__(message)


class NoAppointmentsSelectedError(Exception):
    def __init__(self, message: str = "No selected appointments found for the specified date."):
        super().__init__(message)


class NoActiveRunError(Exception):
    def __init__(self, message: str = "No active process"):
        super().__init__(message)


class NotFoundError(Exception):
    pass


class InvalidRequestError(Exception):
    pass
