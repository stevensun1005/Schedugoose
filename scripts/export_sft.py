"""Export collected interactions into a supervised-finetuning dataset.

    python -m scripts.export_sft --out data/sft_dataset.jsonl            # all turns
    python -m scripts.export_sft --out data/sft_good.jsonl --rated-only  # 👍 only
"""

from __future__ import annotations

import argparse

from data.feedback import export_sft


def main() -> int:
    p = argparse.ArgumentParser(description="Build an SFT dataset from logged interactions.")
    p.add_argument("--out", default="data/sft_dataset.jsonl")
    p.add_argument("--src", default=None, help="interactions.jsonl path (default: FEEDBACK_LOG)")
    p.add_argument("--rated-only", action="store_true", help="keep only positively-rated turns")
    args = p.parse_args()

    n = export_sft(args.out, src=args.src, min_reward=1 if args.rated_only else None)
    print(f"Wrote {n} SFT examples to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
