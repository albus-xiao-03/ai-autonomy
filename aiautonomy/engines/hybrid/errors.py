"""Errors a hybrid run raises for requests it refuses (mapped to HTTP by the API).

REQ: ARCH-02
"""

from aiautonomy.engines.contract.common import Failure


class RunError(Exception):
    """A request the run refuses: 404, 409 (conflict with the run state) or 422 (invalid)."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        failures: list[Failure] | None = None,
        entity_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.failures = failures or []
        self.entity_id = entity_id
