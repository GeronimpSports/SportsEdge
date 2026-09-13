#!/usr/bin/env python3
"""Capture VSiN Circa Friday Football Invitational pick-frequency context.

This lane is commentary/diagnostic context only. Contestant pick percentages are
handicapper contest selections, NOT sportsbook ticket percentages and NOT handle.
Nothing emitted here has Model_P, Truth Gate, promotion, eligibility, staking,
confidence, edge-floor, or OFFICIAL authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

POLICY_ID = "FOOTBALL_EXTERNAL_CONTEXT_V1"
SOURCE_ID = "VSIN_CIRCA_FRIDAY_FOOTBALL_INVITATIONAL_2026"
DEFAULT_URL = "https://data.vsin.com/procontests/circa-friday-football-invitational-2026/games/splits/"


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "SportsEdge/1.0 external-context"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read()


def parse_summary(raw: bytes) -> dict[str, object]:
    parser = TextExtractor()
    parser.feed(raw.decode("utf-8", errors="replace"))
    text = " ".join(parser.parts)
    if "Circa Football Invitational 2026" not in text:
        raise RuntimeError("VSIN_CONTEST_PAGE_IDENTITY_MISMATCH")

    week_match = re.search(r"Week\s+(\d+)\s+Splits", text, re.I)
    updated_match = re.search(r"Updated\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})", text, re.I)
    counts_match = re.search(r"All\s+(\d+)\s+NFL\s+(\d+)\s+CFB\s+(\d+)", text, re.I)

    return {
        "contest_week": int(week_match.group(1)) if week_match else None,
        "updated_at_source": updated_match.group(1) if updated_match else None,
        "listed_games_all": int(counts_match.group(1)) if counts_match else None,
        "listed_games_nfl": int(counts_match.group(2)) if counts_match else None,
        "listed_games_cfb": int(counts_match.group(3)) if counts_match else None,
        "page_identity_verified": True,
    }


def build_manifest(raw: bytes, url: str, captured_at: datetime) -> dict[str, object]:
    summary = parse_summary(raw)
    return {
        "schema_version": "SPORTSEDGE_EXTERNAL_CONTEXT_SNAPSHOT_V1",
        "policy_id": POLICY_ID,
        "source_id": SOURCE_ID,
        "source_url": url,
        "captured_at": captured_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "raw_sha256": hashlib.sha256(raw).hexdigest(),
        "raw_bytes": len(raw),
        "source_type": "HANDICAPPER_CONTEST_PICK_FREQUENCY",
        "semantics": "contest entrant selection frequency; not sportsbook tickets or money/handle",
        "context_only": True,
        "model_p_authority": False,
        "predictive_model_input": False,
        "truth_gate_input": False,
        "promotion_authority": False,
        "eligibility_authority": False,
        "edge_floor_authority": False,
        "staking_authority": False,
        "official_authority": False,
        "confidence_vote": False,
        **summary,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--now", help="ISO timestamp override for deterministic tests")
    ap.add_argument("--raw-file", help="Use local HTML instead of network fetch")
    args = ap.parse_args()

    now = datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise SystemExit("CAPTURE_TIME_MUST_BE_TIMEZONE_AWARE")
    raw = Path(args.raw_file).read_bytes() if args.raw_file else fetch(args.url)
    manifest = build_manifest(raw, args.url, now)

    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    root = Path(args.out_dir) / "archive" / "external-context" / "vsin-circa-ffi-2026" / day
    root.mkdir(parents=True, exist_ok=True)
    raw_path = root / f"{stamp}.html"
    manifest_path = root / f"{stamp}.json"
    raw_path.write_bytes(raw)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"raw": str(raw_path), "manifest": str(manifest_path), **manifest}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
