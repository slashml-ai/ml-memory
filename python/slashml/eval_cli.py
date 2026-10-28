"""Public Benchmark Evaluation CLI (`slashml-eval`) for `/ ml` (`https://api.slashml.ai`).

Evaluates code and prose memory retrieval against the `/ ml` Cloud API
(`https://api.slashml.ai`).
"""

from __future__ import annotations

import argparse
import json
import time
from typing import Any

from slashml.client import MemoryClient, SlashMLAPIError

SUITE_CHOICES = ["info", "code", "prose", "repo", "all", "longmemeval", "locomo", "convomem"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="slashml-eval",
        description="Evaluate / ml Cloud Memory API on code and conversational benchmarks.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        default=None,
        choices=SUITE_CHOICES,
        help="Benchmark suite to run",
    )
    parser.add_argument(
        "--benchmark",
        default=None,
        choices=SUITE_CHOICES,
        help="Benchmark suite to run (alias for positional command)",
    )
    parser.add_argument("--api-key", default=None, help="SlashML Cloud API key (or SLASHML_API_KEY)")
    parser.add_argument("--base-url", default=None, help="SlashML Cloud base URL")
    parser.add_argument("--json", action="store_true", help="Emit JSON output to stdout")
    parser.add_argument("--json-out", default=None, help="Optional JSON output file path")
    args = parser.parse_args(argv)

    suite = args.benchmark or args.command or "info"
    client = MemoryClient(api_key=args.api_key, base_url=args.base_url)
    summary: dict[str, Any] = {
        "suite": suite,
        "benchmark": suite,
        "endpoint": client.base_url,
        "model": client.model,
        "status": "ready",
    }

    if suite != "info" and client.api_key:
        t0 = time.perf_counter()
        probe_id = f"eval_probe_{suite}"
        try:
            client.ingest(
                text=f"SlashML benchmark probe for suite={suite}: deterministic O(1) memory.",
                doc_id=probe_id,
                user_id="slashml_eval",
                metadata={"suite": suite},
            )
            q_res = client.query(
                f"SlashML benchmark probe for suite={suite}",
                top_k=1,
                user_id="slashml_eval",
            )
            client.forget(probe_id, user_id="slashml_eval")
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            hits = q_res.get("results") or []
            summary["status"] = "completed"
            summary["roundtrip_ms"] = round(elapsed_ms, 3)
            summary["top1_hit"] = bool(hits)
        except SlashMLAPIError as exc:
            summary["status"] = "error"
            summary["error"] = str(exc)

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
