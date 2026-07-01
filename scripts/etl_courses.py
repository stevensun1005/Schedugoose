"""CLI for the course-knowledge ETL pipeline.

Extract course docs → chunk → embed → load into a vector store.

    python -m scripts.etl_courses --out data/vector_store.json
    python -m scripts.etl_courses --mongo          # load into MongoDB when configured
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import asdict

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

from data.etl import run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest course documents into the RAG vector store.")
    parser.add_argument("--out", default="data/vector_store.json", help="JSON output path")
    parser.add_argument("--mongo", action="store_true", help="load into MongoDB (MONGODB_URI) instead of JSON")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    stats = run_pipeline(out_path=args.out, to_mongo=args.mongo)
    print("ETL complete:")
    for k, v in asdict(stats).items():
        print(f"  {k:20} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
