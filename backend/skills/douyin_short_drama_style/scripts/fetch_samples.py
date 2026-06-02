"""Placeholder crawler for Douyin-style short-drama samples.

Future implementation can call a compliant provider API, normalize public sample
metadata, and return structural references for style analysis. The current
placeholder is intentionally side-effect free.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

PLATFORM = "douyin"


def fetch_samples(keyword: str, limit: int = 5) -> list[dict[str, Any]]:
    """Return normalized sample metadata for future style analysis."""
    _ = (keyword, limit)
    return []


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Douyin short-drama samples.")
    parser.add_argument("--keyword", default="", help="Topic or keyword to search.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum sample count.")
    args = parser.parse_args()
    print(json.dumps(fetch_samples(args.keyword, args.limit), ensure_ascii=False))


if __name__ == "__main__":
    main()
