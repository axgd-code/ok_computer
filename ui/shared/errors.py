class AppError(Exception):
    def __init__(self, message, status=400, code='app_error'):
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code


class ValidationError(AppError):
    def __init__(self, message, code='validation_error'):
        super().__init__(message, status=400, code=code)


class NotFoundError(AppError):
    def __init__(self, message, code='not_found'):
        super().__init__(message, status=404, code=code)


class ExternalServiceError(AppError):
    def __init__(self, message, status=502, code='external_service_error'):
        super().__init__(message, status=status, code=code)
