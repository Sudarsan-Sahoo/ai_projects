from __future__ import annotations

import argparse
import sys
from pathlib import Path

from support_ticket_ai.config import apply_openai_env, load_json_config, openai_config_from_dict
from support_ticket_ai.paths import data_dir, outputs_dir
from support_ticket_ai.pipeline import PipelinePaths, run_offline, run_online


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Support-ticket intelligence pipeline (offline-first)."
    )
    mode = p.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Run without API calls using precomputed outputs (default).",
    )
    mode.add_argument(
        "--online",
        action="store_true",
        help="Run the full pipeline with API calls (requires credentials).",
    )

    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional path to a JSON config file (recommended: `config.json`, gitignored).",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=data_dir() / "support_ticket_data.csv",
        help="Path to the ticket CSV input.",
    )
    p.add_argument(
        "--outdir",
        type=Path,
        default=outputs_dir(),
        help="Directory to write outputs to.",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional row limit for quick runs (online mode).",
    )
    p.add_argument("--summary-model", type=str, default="gpt-4o-mini")
    p.add_argument("--eval-model", type=str, default="gpt-4o")
    p.add_argument("--reply-model", type=str, default="gpt-4o")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)

    if args.config is not None:
        cfg_dict = load_json_config(args.config)
        apply_openai_env(openai_config_from_dict(cfg_dict))

    if args.online:
        result = run_online(
            PipelinePaths(data_csv=args.data, out_dir=args.outdir),
            limit=args.limit,
            summary_model=args.summary_model,
            eval_model=args.eval_model,
            reply_model=args.reply_model,
        )
        print(f"Wrote: {result['consolidated_csv']}")
        print(f"Wrote: {result['final_csv']}")
        return 0

    report_path = run_offline(out_dir=args.outdir)
    print(f"Wrote: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

