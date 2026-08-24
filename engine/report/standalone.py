"""One self-contained dashboard file.

The application is how the report is produced. This is how a result travels:
a single ``.html`` file with the page, its styling, its behaviour and its data
all inside it. It opens by double-clicking, from anywhere - an email, a shared
drive, a phone - with no application, no server and no internet.

It is read-only by construction: the data is baked in, so there is nothing to
process and no way to change a number.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "webapp", "static")


def _read(name: str) -> str:
    with open(os.path.join(STATIC_DIR, name), "r", encoding="utf-8") as handle:
        return handle.read()


def build(document: dict, title: str | None = None) -> str:
    """Return the complete HTML for ``document``."""

    html = _read("index.html")
    styles = _read("styles.css")
    script = _read("app.js")

    payload = json.dumps(document, ensure_ascii=False, default=str)
    # </script> inside the data would end the block early.
    payload = payload.replace("</", "<\\/")

    saved_at = _dt.datetime.now().isoformat(timespec="seconds")
    banner = json.dumps({"saved_at": saved_at}, ensure_ascii=False)

    html = html.replace('<link rel="stylesheet" href="/styles.css">',
                        "<style>\n" + styles + "\n</style>")
    html = html.replace('<script src="/app.js"></script>',
                        "<script>window.__DASHBOARD__ = " + payload + ";\n"
                        "window.__SAVED_COPY__ = " + banner + ";</script>\n"
                        "<script>\n" + script + "\n</script>")
    if title:
        html = re.sub(r"<title>.*?</title>", "<title>" + _escape(title) + "</title>", html,
                      count=1, flags=re.S)
    return html



def verify(html: str, document: dict) -> None:
    """Refuse a generated report that is incomplete or depends on the internet."""

    if "window.__DASHBOARD__" not in html or len(html) < 10000:
        raise ValueError("standalone dashboard is incomplete")
    if 'href="/styles.css"' in html or 'src="/app.js"' in html:
        raise ValueError("standalone dashboard still contains external local assets")
    # The SVG namespace string is metadata, not a network request. Everything else must be local.
    urls = re.findall(r"https?://[^\s\"'()<>\\]+", html)
    external = [url for url in urls if not url.startswith("http://www.w3.org")]
    if external:
        raise ValueError(f"standalone dashboard references the internet: {external[:3]}")
    run_id = str((document.get("run") or {}).get("run_id", ""))
    if run_id and run_id not in html:
        raise ValueError("standalone dashboard does not carry the current run")

def _escape(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def file_name(project_name: str, document: dict) -> str:
    run = (document.get("run") or {}).get("finished_at") or ""
    stamp = run[:10].replace("-", "") or _dt.date.today().strftime("%Y%m%d")
    safe = "".join(ch for ch in str(project_name) if ch.isalnum() or ch in "-_")
    return f"{safe or 'Report'}_{stamp}.html"
