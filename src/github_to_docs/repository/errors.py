"""Errors raised by the repository acquisition module."""

from __future__ import annotations


class RepositoryAcquisitionError(RuntimeError):
    """Base error for repository acquisition failures."""


class RepositoryNotFoundError(RepositoryAcquisitionError):
    """The repository does not exist or is inaccessible."""


class RepositoryRateLimitedError(RepositoryAcquisitionError):
    """GitHub API rate limit was hit."""


class RepositoryTooLargeError(RepositoryAcquisitionError):
    """Repository exceeds configured size limits."""


class NetworkError(RepositoryAcquisitionError):
    """A network error occurred while retrieving the repository."""


class UnexpectedRepositoryError(RepositoryAcquisitionError):
    """The acquisition silently resolved to an unexpected repository/branch."""
