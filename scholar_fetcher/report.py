"""What one fetch actually did.

Every source returns a FetchReport rather than a bare list, so a caller can
always tell a complete result set from a truncated one. Collapsing those two
into the same return value is how a run that lost half its pages used to pass
for a finished search.
"""

from dataclasses import dataclass, field


class FetchError(RuntimeError):
    """A source failure that retrying will not fix (bad key, exhausted plan).

    Carries the rows collected before the failure so a caller can keep what it
    already paid for instead of discarding a partial corpus.
    """

    def __init__(self, message: str, report: "FetchReport"):
        super().__init__(message)
        self.report = report


@dataclass
class FetchReport:
    """The numbers a caller must be able to report for one source."""

    results: list[dict] = field(default_factory=list)
    requested: int = 0
    pages_ok: int = 0
    pages_failed: int = 0
    failed_offsets: list[int] = field(default_factory=list)
    source: str = "unknown"

    @property
    def collected(self) -> int:
        return len(self.results)

    @property
    def complete(self) -> bool:
        """False when any page was lost, i.e. the row count understates reality."""
        return self.pages_failed == 0
