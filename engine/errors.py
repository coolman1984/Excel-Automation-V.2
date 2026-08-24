"""Plain-language errors.

Every failure the final user can see must answer four questions:

1. what happened (plain language);
2. is previously trusted data still safe;
3. what is the one next action;
4. what support code identifies the problem.

Technical detail is kept in ``detail`` and is only shown collapsed.
"""

from __future__ import annotations

import dataclasses
from typing import Any


@dataclasses.dataclass
class UserError(Exception):
    """An error that is safe to show to a non-technical user."""

    code: str
    what_happened: str
    next_action: str
    trusted_data_safe: bool = True
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.code}] {self.what_happened}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "support_code": self.code,
            "what_happened": self.what_happened,
            "trusted_data_safe": self.trusted_data_safe,
            "next_action": self.next_action,
            "detail": self.detail,
        }


# Support codes are stable. Never reuse a code for a different meaning.
CODES = {
    "E-CFG-001": "Project configuration file is missing.",
    "E-CFG-002": "Project configuration is not valid JSON.",
    "E-CFG-003": "Project configuration is missing a required setting.",
    "E-CFG-004": "Project configuration contains an unknown setting.",
    "E-CFG-005": "Business meaning is still waiting for approval.",
    "E-IN-001": "No input file was found for a required source.",
    "E-IN-002": "An input file could not be opened.",
    "E-IN-003": "An expected column is missing from an input file.",
    "E-IN-004": "An input file changed while it was being read.",
    "E-VAL-001": "Rows failed the agreed quality rules.",
    "E-REC-001": "Totals did not reconcile.",
    "E-HIST-001": "Trusted history could not be updated.",
    "E-SQL-001": "A project calculation failed.",
    "E-PKG-001": "The delivered package does not have the approved shape.",
    "E-RUN-001": "The run stopped before it finished.",
}


def user_error(code: str, next_action: str, detail: str = "", trusted_data_safe: bool = True,
               what_happened: str | None = None) -> UserError:
    """Build a :class:`UserError` from the registry of support codes."""

    return UserError(
        code=code,
        what_happened=what_happened or CODES.get(code, "Something went wrong."),
        next_action=next_action,
        trusted_data_safe=trusted_data_safe,
        detail=detail,
    )
