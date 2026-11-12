from __future__ import annotations

import argparse
import json
from pathlib import Path

from .mock_runner import run_mock_call


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an approved Hawlak call plan locally")
    parser.add_argument("plan", type=Path, help="Path to a synthetic approved call-plan JSON")
    parser.add_argument(
        "--answers",
        required=True,
        help="Comma-separated clear,red_flag,uncertain,transfer_request answers",
    )
    args = parser.parse_args()
    payload = json.loads(args.plan.read_text())
    result = run_mock_call(
        plan_payload=payload,
        answers=[answer.strip() for answer in args.answers.split(",")],
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
