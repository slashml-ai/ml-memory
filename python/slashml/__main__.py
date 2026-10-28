"""CLI entrypoint for `python -m slashml`."""

from __future__ import annotations

import sys

from slashml.mcp_server import main


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
