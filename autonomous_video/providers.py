from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import GameRecord


class GameProvider(Protocol):
    def list_games(self) -> list[GameRecord]: ...


class GameDataProvider(Protocol):
    def ingest_game(self, game: GameRecord) -> dict[str, Any]: ...


class FixtureProvider:
    """Deterministic provider used to prove the automation backbone."""

    def __init__(self, fixture_path: str | Path):
        self.fixture_path = Path(fixture_path)
        self.payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))

    def list_games(self) -> list[GameRecord]:
        return [GameRecord(**game) for game in self.payload["games"]]

    def ingest_game(self, game: GameRecord) -> dict[str, Any]:
        plays = [p for p in self.payload.get("plays", []) if str(p["game_id"]) == str(game.game_id)]
        return {
            "source": self.payload.get("source", "fixture"),
            "game": {
                "game_id": game.game_id,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "home_score": game.home_score,
                "away_score": game.away_score,
            },
            "plays": plays,
            "play_count": len(plays),
        }


class CfbdProvider:
    """CollegeFootballData adapter using documented /games and /plays endpoints."""

    BASE_URL = "https://api.collegefootballdata.com"

    def __init__(self, *, year: int, week: int, team: str | None = None, api_key: str | None = None):
        self.year = year
        self.week = week
        self.team = team
        self.api_key = api_key or os.getenv("CFBD_API_KEY")
        if not self.api_key:
            raise RuntimeError("CFBD_API_KEY is required for live CFBD ingestion")

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        req = Request(
            f"{self.BASE_URL}{path}?{query}",
            headers={"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"},
        )
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    def list_games(self) -> list[GameRecord]:
        payload = self._get("/games", {"year": self.year, "week": self.week, "team": self.team})
        games: list[GameRecord] = []
        for raw in payload:
            completed = bool(raw.get("completed"))
            games.append(
                GameRecord(
                    game_id=str(raw["id"]),
                    season=int(raw.get("season", self.year)),
                    week=int(raw.get("week", self.week)),
                    home_team=raw["homeTeam"],
                    away_team=raw["awayTeam"],
                    status="FINAL" if completed else str(raw.get("status") or "SCHEDULED"),
                    home_score=raw.get("homePoints"),
                    away_score=raw.get("awayPoints"),
                    start_time=raw.get("startDate"),
                    source="cfbd",
                )
            )
        return games

    def ingest_game(self, game: GameRecord) -> dict[str, Any]:
        payload = self._get(
            "/plays",
            {"year": game.season, "week": game.week, "team": self.team or game.home_team},
        )
        plays = [p for p in payload if str(p.get("gameId")) == str(game.game_id)]
        return {"source": "cfbd", "game_id": game.game_id, "plays": plays, "play_count": len(plays)}
