#!/usr/bin/env python3
"""CLI shim for :mod:`freeciv_agent.events.synthetic`."""

import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SRC = os.path.join(_REPO, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from freeciv_agent.events.synthetic import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
