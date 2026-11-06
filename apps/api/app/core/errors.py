"""Typed application errors mapped to a consistent JSON envelope by the API."""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"


class ValidationAppError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


class ProviderNotConfiguredError(AppError):
    status_code = 409
    code = "provider_not_configured"


class ProviderFailureError(AppError):
    status_code = 502
    code = "provider_failure"


class BudgetExceededError(AppError):
    status_code = 402
    code = "budget_exceeded"


class WorkflowStateError(AppError):
    status_code = 409
    code = "invalid_workflow_state"
