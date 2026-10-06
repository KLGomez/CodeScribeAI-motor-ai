class ServiceException(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class GitHubRateLimitException(ServiceException):
    def __init__(self, message: str = "GitHub ha limitado temporalmente las consultas. Por favor, espera unos minutos o conecta tu cuenta."):
        super().__init__(code="GITHUB_RATE_LIMIT", message=message, status_code=429)


class RepoNotFoundException(ServiceException):
    def __init__(self, message: str = "El repositorio solicitado no existe o no tienes permisos para acceder a él."):
        super().__init__(code="REPO_NOT_FOUND", message=message, status_code=404)


class RepoEmptyException(ServiceException):
    def __init__(self, message: str = "El repositorio no contiene archivos de código analizables."):
        super().__init__(code="REPO_EMPTY", message=message, status_code=422)


class AiTimeoutException(ServiceException):
    def __init__(self, message: str = "El tiempo de espera para generar la documentación ha expirado."):
        super().__init__(code="AI_TIMEOUT", message=message, status_code=504)


class AiUnavailableException(ServiceException):
    def __init__(self, message: str = "El servicio de IA no está disponible temporalmente."):
        super().__init__(code="AI_UNAVAILABLE", message=message, status_code=503)


class AiBusyException(ServiceException):
    def __init__(self, message: str = "El motor está al máximo de su capacidad. Reintenta en unos instantes."):
        super().__init__(code="AI_BUSY", message=message, status_code=503)
