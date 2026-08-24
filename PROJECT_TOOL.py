#!/usr/bin/env python3
"""PROJECT_TOOL entry point. Run: python PROJECT_TOOL.py <command>"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
