"""A plain-text alert for a scheduled run nobody was watching.

``--run-once`` exists for Windows Task Scheduler: it normally runs under
``pythonw.exe``, which has no console at all, so a failure there is otherwise
completely invisible until someone happens to open the report and notices the
numbers are stale. This writes one file, right next to ``START.bat`` where it
cannot be missed, and removes it automatically the next time a run actually
succeeds - so it only ever appears when there is something to act on.
"""

from __future__ import annotations

import datetime as _dt
import os

FILENAME = "NEEDS_ATTENTION.txt"


def path(package_root: str) -> str:
    return os.path.join(package_root, FILENAME)


def write(package_root: str, title: str, what_happened: str, next_action: str,
          support_code: str = "") -> None:
    """Record that an unattended run needs a person's attention.

    Best-effort: a scheduled run that cannot even write this file is no worse
    off than before this feature existed, so failures here are swallowed
    rather than turned into a second problem.
    """

    lines = [
        f"{title}: the last automatic update did not finish.",
        "",
        f"When: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "What happened:",
        f"  {what_happened}",
        "",
        "What to do:",
        f"  {next_action}",
    ]
    if support_code:
        lines += ["", f"Support code: {support_code}"]
    lines += [
        "",
        "Your previous results are unaffected - this only means today's update "
        "did not go through.",
        "",
        "This note disappears by itself the next time an update succeeds; you "
        "do not need to delete it.",
    ]
    try:
        os.makedirs(package_root, exist_ok=True)
        with open(path(package_root), "w", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def clear(package_root: str) -> None:
    try:
        os.remove(path(package_root))
    except OSError:
        pass
