"""Self-contained CLI entrypoint for `slashml-eval` (`https://api.slashml.ai`).

Works either with `slashml` installed or standalone using Python's standard library.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any


def _standalone_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slashml-eval",
        description="Run public memory benchmarks against `/ ml` Cloud (`https://api.slashml.ai`).",
    )
    parser.add_argument(
        "--benchmark",
        default="all",
        choices=["all", "longmemeval", "locomo", "convomem", "code", "prose"],
        help="Benchmark suite to run via the `/ ml` Cloud API.",
    )
    parser.add_argument("--api-key", default=os.environ.get("SLASHML_API_KEY"), help="SlashML Cloud API key")
    parser.add_argument(
        "--base-url",
        default=os.environ.get("SLASHML_BASE_URL", "https://api.slashml.ai"),
        help="SlashML Cloud base URL",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    if not args.api_key:
        raise ValueError(
            "SlashML API key is required. Set SLASHML_API_KEY in your environment or pass --api-key."
        )

    req = urllib.request.Request(
        f"{args.base_url.rstrip('/')}/v1/eval/run",
        data=json.dumps({"benchmark": args.benchmark}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {args.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "slashml-eval/1.0.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30.0) as resp:
        res: dict[str, Any] = json.loads(resp.read().decode("utf-8"))

    if args.json:
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
    else:
        sys.stdout.write(f"/ ml Cloud Benchmark Suite ({args.benchmark}):\n")
        sys.stdout.write(json.dumps(res, indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        from slashml.eval_cli import main as sdk_eval_main

        return sdk_eval_main(argv)
    except ImportError:
        return _standalone_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
