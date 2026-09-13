#!/usr/bin/env python3
"""Inventory scheduled workflows and enforce the frozen cron policy.

Stdlib-only by design. A scheduled workflow must be explicitly allowlisted as
irreversible/PIT-sensitive evidence collection. Everything else belongs on
workflow_dispatch / event triggers.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CRON_RE = re.compile(r"cron:\s*['\"]([^'\"]+)['\"]")


def runs_per_day(expr: str) -> float | None:
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    if dom != "*" or month != "*" or dow != "*":
        return None
    def count(field: str, span: int) -> int | None:
        if field == "*": return span
        if field.startswith("*/"):
            try: return max(1, span // int(field[2:]))
            except Exception: return None
        vals = field.split(",")
        if all(v.isdigit() for v in vals): return len(vals)
        return None
    m = count(minute, 60); h = count(hour, 24)
    return float(m*h) if m is not None and h is not None else None


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", default=".")
    p.add_argument("--policy", default="config/workflow_cron_policy_v1.json")
    p.add_argument("--out", default="artifacts/audit/workflow_cron_census.json")
    args = p.parse_args()

    root = Path(args.repo_root)
    policy = json.loads((root / args.policy).read_text(encoding="utf-8"))
    if policy.get("policy_id") != "SPORTSEDGE_WORKFLOW_CRON_POLICY_V1":
        raise SystemExit("WORKFLOW_CRON_POLICY_ID_MISMATCH")
    allowed = set(policy.get("allowed_scheduled_workflows") or [])

    rows = []
    total = 0.0
    violations = []
    for path in sorted((root / ".github/workflows").glob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        exprs = CRON_RE.findall(text)
        if not exprs:
            continue
        rel = path.relative_to(root).as_posix()
        estimates = [runs_per_day(x) for x in exprs]
        daily = sum(x for x in estimates if x is not None)
        total += daily
        approved = rel in allowed
        row = {"workflow": rel, "cron": exprs, "estimated_runs_per_day": daily, "approved": approved}
        rows.append(row)
        if not approved:
            violations.append(rel)

    payload = {
        "policy_id": policy["policy_id"],
        "scheduled_workflow_count": len(rows),
        "estimated_scheduled_runs_per_day": total,
        "workflows": rows,
        "violations": violations,
        "status": "PASS" if not violations else "FAIL",
    }
    out = root / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not violations else 2

if __name__ == "__main__":
    raise SystemExit(main())
