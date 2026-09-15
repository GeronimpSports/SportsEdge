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


class EspnPublicProvider:
    """Zero-key ESPN public-data fallback for low-intervention operation.

    ESPN does not document these public site endpoints as a supported developer
    API, so production should retain a second source for verification.
    """

    SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
    SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/college-football/summary"

    def __init__(self, *, date: str, team: str | None = None, groups: int = 80):
        self.date = date.replace("-", "")
        self.team = team
        self.groups = groups

    def _get_url(self, base: str, params: dict[str, Any]) -> Any:
        query = urlencode({k: v for k, v in params.items() if v is not None})
        req = Request(
            f"{base}?{query}",
            headers={"Accept": "application/json", "User-Agent": "SportsEdgePostgameVideo/0.2"},
        )
        with urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _team_name(competitor: dict[str, Any]) -> str:
        team = competitor.get("team") or {}
        return str(team.get("displayName") or team.get("shortDisplayName") or team.get("name") or team.get("abbreviation"))

    def list_games(self) -> list[GameRecord]:
        payload = self._get_url(
            self.SCOREBOARD_URL,
            {"dates": self.date, "groups": self.groups, "limit": 1000},
        )
        games: list[GameRecord] = []
        for event in payload.get("events", []):
            competitions = event.get("competitions") or []
            if not competitions:
                continue
            competition = competitions[0]
            competitors = competition.get("competitors") or []
            home = next((c for c in competitors if c.get("homeAway") == "home"), None)
            away = next((c for c in competitors if c.get("homeAway") == "away"), None)
            if not home or not away:
                continue

            home_team = self._team_name(home)
            away_team = self._team_name(away)
            if self.team:
                wanted = self.team.casefold()
                if wanted not in home_team.casefold() and wanted not in away_team.casefold():
                    continue

            status_type = ((event.get("status") or {}).get("type") or {})
            completed = bool(status_type.get("completed"))
            status_name = str(status_type.get("name") or "")
            status = "FINAL" if completed or status_name == "STATUS_FINAL" else status_name or "SCHEDULED"

            season = event.get("season") or {}
            week = (payload.get("week") or {}).get("number") or 0
            games.append(
                GameRecord(
                    game_id=str(event["id"]),
                    season=int(season.get("year") or self.date[:4]),
                    week=int(week),
                    home_team=home_team,
                    away_team=away_team,
                    status=status,
                    home_score=int(home["score"]) if str(home.get("score", "")).isdigit() else None,
                    away_score=int(away["score"]) if str(away.get("score", "")).isdigit() else None,
                    start_time=event.get("date"),
                    source="espn_public",
                )
            )
        return games

    def ingest_game(self, game: GameRecord) -> dict[str, Any]:
        payload = self._get_url(self.SUMMARY_URL, {"event": game.game_id})
        header_competitions = ((payload.get("header") or {}).get("competitions") or [])
        competitors = header_competitions[0].get("competitors", []) if header_competitions else []
        names_by_id = {}
        for c in competitors:
            team = c.get("team") or {}
            if team.get("id") is not None:
                names_by_id[str(team["id"])] = str(
                    team.get("displayName") or team.get("shortDisplayName") or team.get("abbreviation")
                )

        mapped: list[dict[str, Any]] = []
        for raw in payload.get("plays", []) or []:
            team_obj = raw.get("team") or {}
            offense = names_by_id.get(str(team_obj.get("id"))) if team_obj.get("id") is not None else None
            if offense is None:
                offense = team_obj.get("displayName") or team_obj.get("abbreviation")
            defense = None
            if offense:
                defense = game.away_team if offense == game.home_team else game.home_team

            start = raw.get("start") or {}
            period = raw.get("period") or {}
            clock = raw.get("clock") or {}
            play_type = raw.get("type") or {}
            mapped.append(
                {
                    "game_id": game.game_id,
                    "id": raw.get("id"),
                    "period": period.get("number") if isinstance(period, dict) else period,
                    "clock": clock.get("displayValue") if isinstance(clock, dict) else clock,
                    "offense": offense,
                    "defense": defense,
                    "down": start.get("down"),
                    "distance": start.get("distance"),
                    "yards_gained": raw.get("statYardage"),
                    "play_type": play_type.get("text") if isinstance(play_type, dict) else play_type,
                    "play_text": raw.get("text"),
                }
            )

        return {
            "source": "espn_public",
            "source_warning": "Public ESPN site endpoint; verify important facts against a second source.",
            "game_id": game.game_id,
            "plays": mapped,
            "play_count": len(mapped),
        }
