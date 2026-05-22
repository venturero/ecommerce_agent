"""Aggregate launch metrics from SQLite and print or export summaries."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .event_db import backup_db, export_db_json, get_db_path, init_db
from .query_metrics import is_failure_outcome

_FAILURE_OUTCOMES_SQL = (
    "'search_failed', 'error', 'rate_limited', 'session_unavailable', "
    "'empty_shortlist', 'low_relevance'"
)


def build_metrics_summary(db_path: Path | None = None) -> dict[str, Any]:
    path = init_db(db_path)
    with sqlite3.connect(path) as conn:
        impressions = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'impression'")
        clicks = _scalar(conn, "SELECT COUNT(*) FROM events WHERE event_type = 'product_click'")
        ctr = round(clicks / impressions, 4) if impressions else None

        sessions_with_messages = _scalar(
            conn,
            "SELECT COUNT(DISTINCT session_id) FROM events WHERE event_type = 'message_send'",
        )
        follow_up_sessions = _scalar(
            conn,
            """
            SELECT COUNT(*) FROM (
                SELECT session_id FROM events
                WHERE event_type = 'message_send'
                GROUP BY session_id
                HAVING COUNT(*) > 1
            )
            """,
        )
        follow_up_rate = (
            round(follow_up_sessions / sessions_with_messages, 4)
            if sessions_with_messages
            else None
        )

        query_requests = _scalar(conn, "SELECT COUNT(*) FROM query_requests")
        follow_up_requests = _scalar(
            conn, "SELECT COUNT(*) FROM query_requests WHERE is_follow_up = 1"
        )
        request_follow_up_rate = (
            round(follow_up_requests / query_requests, 4) if query_requests else None
        )

        latency = conn.execute(
            """
            SELECT
                COUNT(*) AS n,
                ROUND(AVG(total_s), 3) AS avg_total_s,
                ROUND(AVG(ttfb_s), 3) AS avg_ttfb_s,
                ROUND(MAX(total_s), 3) AS max_total_s
            FROM query_requests
            """
        ).fetchone()

        p95_total_s = _percentile(conn, "total_s", 0.95)
        p95_ttfb_s = _percentile(conn, "ttfb_s", 0.95)

        failures_by_query = [
            {
                "query_text": row[0],
                "failure_count": row[1],
                "outcomes": row[2],
            }
            for row in conn.execute(
                f"""
                SELECT query_text, COUNT(*) AS n, GROUP_CONCAT(DISTINCT outcome) AS outcomes
                FROM query_requests
                WHERE outcome IN ({_FAILURE_OUTCOMES_SQL})
                GROUP BY query_text
                ORDER BY n DESC, query_text
                LIMIT 15
                """
            )
        ]

        slow_queries = [
            {
                "query_text": row[0],
                "total_s": row[1],
                "path": row[2],
                "outcome": row[3],
                "session_id": row[4],
            }
            for row in conn.execute(
                """
                SELECT query_text, total_s, path, outcome, session_id
                FROM query_requests
                ORDER BY total_s DESC
                LIMIT 10
                """
            )
        ]

        low_ctr_sessions = [
            {
                "session_id": row[0],
                "impressions": row[1],
                "clicks": row[2],
                "ctr": round(row[2] / row[1], 4) if row[1] else None,
            }
            for row in conn.execute(
                """
                SELECT
                    i.session_id,
                    i.impressions,
                    COALESCE(c.clicks, 0) AS clicks
                FROM (
                    SELECT session_id, COUNT(*) AS impressions
                    FROM events WHERE event_type = 'impression'
                    GROUP BY session_id
                    HAVING impressions >= 3
                ) i
                LEFT JOIN (
                    SELECT session_id, COUNT(*) AS clicks
                    FROM events WHERE event_type = 'product_click'
                    GROUP BY session_id
                ) c ON c.session_id = i.session_id
                WHERE COALESCE(c.clicks, 0) * 1.0 / i.impressions < 0.1
                ORDER BY i.impressions DESC
                LIMIT 10
                """
            )
        ]

        outcome_counts = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT outcome, COUNT(*) FROM query_requests GROUP BY outcome ORDER BY COUNT(*) DESC"
            )
        }

    return {
        "db_path": str(path),
        "engagement": {
            "impressions": impressions,
            "clicks": clicks,
            "ctr": ctr,
            "sessions_with_messages": sessions_with_messages,
            "follow_up_sessions": follow_up_sessions,
            "follow_up_rate_by_session": follow_up_rate,
            "query_requests": query_requests,
            "follow_up_requests": follow_up_requests,
            "follow_up_rate_by_request": request_follow_up_rate,
        },
        "latency": {
            "request_count": latency[0] if latency else 0,
            "avg_total_s": latency[1] if latency else None,
            "avg_ttfb_s": latency[2] if latency else None,
            "max_total_s": latency[3] if latency else None,
            "p95_total_s": p95_total_s,
            "p95_ttfb_s": p95_ttfb_s,
        },
        "outcomes": outcome_counts,
        "top_failure_queries": failures_by_query,
        "slow_queries": slow_queries,
        "low_ctr_sessions": low_ctr_sessions,
    }


def format_report_text(summary: dict[str, Any]) -> str:
    eng = summary["engagement"]
    lat = summary["latency"]
    lines = [
        f"Metrics database: {summary['db_path']}",
        "",
        "Engagement",
        f"  Impressions: {eng['impressions']}",
        f"  Clicks: {eng['clicks']}",
        f"  CTR: {eng['ctr']}",
        f"  Sessions with messages: {eng['sessions_with_messages']}",
        f"  Follow-up sessions (>1 message): {eng['follow_up_sessions']}",
        f"  Follow-up rate (by session): {eng['follow_up_rate_by_session']}",
        f"  Chat requests logged: {eng['query_requests']}",
        f"  Follow-up requests: {eng['follow_up_requests']}",
        f"  Follow-up rate (by request): {eng['follow_up_rate_by_request']}",
        "",
        "Latency (query_requests)",
        f"  Requests: {lat['request_count']}",
        f"  Avg total_s: {lat['avg_total_s']}",
        f"  Avg ttfb_s: {lat['avg_ttfb_s']}",
        f"  P95 total_s: {lat['p95_total_s']}",
        f"  P95 ttfb_s: {lat['p95_ttfb_s']}",
        f"  Max total_s: {lat['max_total_s']}",
        "",
        "Outcomes",
    ]
    for outcome, count in summary.get("outcomes", {}).items():
        flag = " (failure)" if is_failure_outcome(outcome) else ""
        lines.append(f"  {outcome}: {count}{flag}")

    lines.extend(["", "Top failure queries (up to 15)"])
    if not summary.get("top_failure_queries"):
        lines.append("  (none)")
    else:
        for row in summary["top_failure_queries"]:
            lines.append(
                f"  [{row['failure_count']}x] {row['query_text']} ({row['outcomes']})"
            )

    lines.extend(["", "Slowest queries (up to 10)"])
    for row in summary.get("slow_queries", []):
        lines.append(
            f"  {row['total_s']:.3f}s {row['outcome']} path={row['path']} "
            f"session={row['session_id'][:8]}… {row['query_text']!r}"
        )

    lines.extend(["", "Low CTR sessions (<10% clicks, ≥3 impressions)"])
    if not summary.get("low_ctr_sessions"):
        lines.append("  (none)")
    else:
        for row in summary["low_ctr_sessions"]:
            lines.append(
                f"  session={row['session_id'][:8]}… "
                f"impressions={row['impressions']} clicks={row['clicks']} ctr={row['ctr']}"
            )
    return "\n".join(lines)


def _scalar(conn: Any, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def _percentile(conn: Any, column: str, fraction: float) -> float | None:
    row = conn.execute(
        f"""
        SELECT {column} FROM query_requests
        WHERE {column} IS NOT NULL
        ORDER BY {column}
        """
    ).fetchall()
    if not row:
        return None
    values = [float(r[0]) for r in row]
    index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
    return round(values[index], 3)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Launch metrics and event DB utilities")
    sub = parser.add_subparsers(dest="command", required=True)

    report_p = sub.add_parser("report", help="Print aggregated metrics summary")
    report_p.add_argument("--json", action="store_true", help="Output JSON instead of text")
    report_p.add_argument("--out", type=Path, help="Write report to file")

    backup_p = sub.add_parser("backup", help="Copy data.db to a timestamped backup file")
    backup_p.add_argument("--dest", type=Path, help="Destination path (default: auto timestamp)")

    export_p = sub.add_parser("export", help="Export events and metrics tables to JSON")
    export_p.add_argument(
        "--out",
        type=Path,
        default=Path("metrics_export.json"),
        help="Output JSON path (default: metrics_export.json)",
    )

    args = parser.parse_args(argv)

    if args.command == "report":
        summary = build_metrics_summary()
        if args.json:
            text = json.dumps(summary, indent=2)
        else:
            text = format_report_text(summary)
        if args.out:
            args.out.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
            print(f"Wrote report to {args.out}", file=sys.stderr)
        else:
            print(text)
        return 0

    if args.command == "backup":
        dest = backup_db(args.dest)
        print(f"Backup written to {dest}")
        print(f"Source: {get_db_path().resolve()}")
        return 0

    if args.command == "export":
        path = export_db_json(args.out)
        print(f"Exported to {path}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
