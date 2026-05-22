from __future__ import annotations

import argparse
import json
import sys

from .agent import ShoppingSearchAgent
from .config import Settings
from .serpapi_client import SerpApiSearchError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="AI-powered shopping search agent")
    parser.add_argument("query", type=str, help="Natural-language shopping request")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    try:
        settings.validate()
    except ValueError as err:
        print(f"Configuration error: {err}", file=sys.stderr)
        return 1

    agent = ShoppingSearchAgent(settings)
    try:
        response = agent.run(args.query)
    except SerpApiSearchError as err:
        print(f"Search failed: {err}", file=sys.stderr)
        return 1
    print(json.dumps(response, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
