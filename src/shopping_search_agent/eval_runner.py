from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent import ShoppingSearchAgent
from .config import Settings
from .eval_checks import run_all_checks
from .serpapi_client import SerpApiSearchError

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "eval" / "prompts.json"
DEFAULT_RESULTS_DIR = REPO_ROOT / "eval" / "results"


def _load_dataset(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _build_follow_up_query(user_query: str, prior_response: dict[str, Any]) -> str:
    constraints = prior_response.get("constraints", {}) or {}
    product_type = str(constraints.get("product_type") or "").strip()
    attributes = constraints.get("attributes") or {}
    budget = constraints.get("budget")

    attr_text = ", ".join(f"{k}={v}" for k, v in attributes.items()) if attributes else ""
    context_parts: list[str] = []
    if product_type:
        context_parts.append(f"product_type={product_type}")
    if attr_text:
        context_parts.append(f"attributes={attr_text}")
    for key in ("brand_include", "brand_exclude", "must_have", "nice_to_have"):
        values = constraints.get(key) or []
        if values:
            context_parts.append(f"{key}={', '.join(str(v) for v in values)}")
    if budget:
        context_parts.append(f"budget={budget}")
    context = "; ".join(context_parts) if context_parts else "same product context as previous turn"
    return f"Follow-up request with previous context [{context}]: {user_query}"


def _shortlist_urls(response: dict[str, Any]) -> list[str]:
    return [str(item.get("url", "")) for item in response.get("shortlist") or []]


def _run_single_case(
    agent: ShoppingSearchAgent,
    case: dict[str, Any],
    *,
    shortlist_min: int,
    shortlist_max: int,
) -> dict[str, Any]:
    prompt_id = str(case["id"])
    category = str(case.get("category", "unknown"))
    query = str(case.get("query", ""))

    if case.get("expect_error") and not query.strip():
        return {
            "id": prompt_id,
            "category": category,
            "query": query,
            "skipped_agent": True,
            "response": None,
            "checks": {"passed": True, "issues": []},
            "error": None,
        }

    prior_query = case.get("prior_query")
    query_to_run = query
    prior_response: dict[str, Any] | None = None

    try:
        if prior_query:
            prior_response = agent.run(str(prior_query))
            query_to_run = _build_follow_up_query(query, prior_response)

        response = agent.run(query_to_run)
        checks = run_all_checks(
            response,
            case,
            shortlist_min=shortlist_min,
            shortlist_max=shortlist_max,
        )
        return {
            "id": prompt_id,
            "category": category,
            "query": query,
            "prior_query": prior_query,
            "executed_query": query_to_run,
            "skipped_agent": False,
            "response": response,
            "checks": checks,
            "error": None,
            "shortlist_count": len(response.get("shortlist") or []),
            "shortlist_urls": _shortlist_urls(response),
        }
    except SerpApiSearchError as err:
        return {
            "id": prompt_id,
            "category": category,
            "query": query,
            "prior_query": prior_query,
            "executed_query": query_to_run,
            "skipped_agent": False,
            "response": None,
            "checks": {"passed": False, "issues": [f"search_error:{err}"]},
            "error": str(err),
            "shortlist_count": 0,
            "shortlist_urls": [],
        }
    except Exception as err:  # pragma: no cover
        return {
            "id": prompt_id,
            "category": category,
            "query": query,
            "prior_query": prior_query,
            "executed_query": query_to_run,
            "skipped_agent": False,
            "response": None,
            "checks": {"passed": False, "issues": [f"unexpected_error:{err}"]},
            "error": str(err),
            "shortlist_count": 0,
            "shortlist_urls": [],
        }


def run_eval(
    *,
    dataset_path: Path,
    output_dir: Path,
    limit: int | None = None,
    category: str | None = None,
) -> Path:
    dataset = _load_dataset(dataset_path)
    prompts = dataset["prompts"]
    shortlist_min = int(dataset.get("shortlist_min", 3))
    shortlist_max = int(dataset.get("shortlist_max", 5))

    if category:
        prompts = [p for p in prompts if p.get("category") == category]
    if limit is not None:
        prompts = prompts[:limit]

    # Align agent shortlist size with eval expectations (default config allows up to 12).
    os.environ["MAX_RECOMMENDED_LINKS"] = str(shortlist_max)
    os.environ["MIN_RECOMMENDED_LINKS"] = str(shortlist_min)

    settings = Settings()
    settings.validate()
    agent = ShoppingSearchAgent(settings)

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / run_id
    responses_dir = run_dir / "responses"
    responses_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for case in prompts:
        row = _run_single_case(
            agent,
            case,
            shortlist_min=shortlist_min,
            shortlist_max=shortlist_max,
        )
        results.append(row)
        response_path = responses_dir / f"{row['id']}.json"
        with open(response_path, "w", encoding="utf-8") as handle:
            json.dump(row, handle, ensure_ascii=False, indent=2)

    passed = sum(1 for row in results if row["checks"]["passed"])
    summary = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset": str(dataset_path),
        "prompt_count": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "shortlist_min": shortlist_min,
        "shortlist_max": shortlist_max,
        "results": results,
    }

    summary_path = run_dir / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    report_path = run_dir / "report.txt"
    _write_report(summary, report_path)

    print(f"Eval run complete: {run_dir}")
    print(f"Passed {passed}/{len(results)}")
    print(f"Summary: {summary_path}")
    print(f"Report: {report_path}")
    return run_dir


def _write_report(summary: dict[str, Any], path: Path) -> None:
    lines = [
        f"Run ID: {summary['run_id']}",
        f"Created: {summary['created_at']}",
        f"Dataset: {summary['dataset']}",
        f"Passed: {summary['passed']}/{summary['prompt_count']}",
        "",
    ]
    for row in summary["results"]:
        status = "PASS" if row["checks"]["passed"] else "FAIL"
        lines.append(f"[{status}] {row['id']} ({row['category']}) — {row['query'][:80]}")
        if not row["checks"]["passed"]:
            for issue in row["checks"]["issues"]:
                lines.append(f"    - {issue}")
        if row.get("error"):
            lines.append(f"    - error: {row['error']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def compare_runs(run_a: Path, run_b: Path) -> dict[str, Any]:
    def load_summary(run_path: Path) -> dict[str, Any]:
        summary_file = run_path / "summary.json"
        if not summary_file.is_file():
            raise FileNotFoundError(f"Missing summary.json in {run_path}")
        with open(summary_file, encoding="utf-8") as handle:
            return json.load(handle)

    summary_a = load_summary(run_a)
    summary_b = load_summary(run_b)

    by_a = {row["id"]: row for row in summary_a["results"]}
    by_b = {row["id"]: row for row in summary_b["results"]}
    all_ids = sorted(set(by_a) | set(by_b))

    comparisons: list[dict[str, Any]] = []
    for prompt_id in all_ids:
        row_a = by_a.get(prompt_id)
        row_b = by_b.get(prompt_id)
        urls_a = row_a.get("shortlist_urls", []) if row_a else []
        urls_b = row_b.get("shortlist_urls", []) if row_b else []
        comparisons.append(
            {
                "id": prompt_id,
                "in_a": row_a is not None,
                "in_b": row_b is not None,
                "passed_a": row_a["checks"]["passed"] if row_a else None,
                "passed_b": row_b["checks"]["passed"] if row_b else None,
                "shortlist_count_a": row_a.get("shortlist_count") if row_a else None,
                "shortlist_count_b": row_b.get("shortlist_count") if row_b else None,
                "urls_changed": urls_a != urls_b,
                "urls_a": urls_a,
                "urls_b": urls_b,
            }
        )

    changed = [c for c in comparisons if c["urls_changed"] or c["passed_a"] != c["passed_b"]]
    report = {
        "run_a": str(run_a),
        "run_b": str(run_b),
        "prompts_compared": len(comparisons),
        "prompts_changed": len(changed),
        "comparisons": comparisons,
    }

    out_path = run_b / "compare_with_previous.json"
    with open(out_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    print(f"Compared {summary_a['run_id']} vs {summary_b['run_id']}")
    print(f"Changed prompts: {len(changed)}/{len(comparisons)}")
    print(f"Report: {out_path}")
    for item in changed[:15]:
        print(
            f"  {item['id']}: pass {item['passed_a']}->{item['passed_b']}, "
            f"urls_changed={item['urls_changed']}"
        )
    if len(changed) > 15:
        print(f"  ... and {len(changed) - 15} more (see JSON)")

    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline evaluation harness for the shopping agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="Run agent against the eval dataset")
    run_parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    run_parser.add_argument("--output", type=Path, default=DEFAULT_RESULTS_DIR)
    run_parser.add_argument("--limit", type=int, default=None, help="Run only the first N prompts")
    run_parser.add_argument("--category", type=str, default=None, help="Filter by category")

    compare_parser = sub.add_parser("compare", help="Compare two eval run directories")
    compare_parser.add_argument("run_a", type=Path)
    compare_parser.add_argument("run_b", type=Path)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "run":
        try:
            run_eval(
                dataset_path=args.dataset,
                output_dir=args.output,
                limit=args.limit,
                category=args.category,
            )
        except ValueError as err:
            print(f"Configuration error: {err}", file=sys.stderr)
            return 1
        return 0

    if args.command == "compare":
        try:
            compare_runs(args.run_a.resolve(), args.run_b.resolve())
        except FileNotFoundError as err:
            print(str(err), file=sys.stderr)
            return 1
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
