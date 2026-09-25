"""Explicit errors for invalid domain operations."""


class InvalidTransition(ValueError):
    """The requested run lifecycle transition is not allowed."""


class NotFound(LookupError):
    """The requested entity does not exist."""


class RevisionConflict(ValueError):
    """The run has changed since the caller read it."""
