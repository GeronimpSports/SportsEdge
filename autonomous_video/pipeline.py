from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from .analytics import build_game_analytics
from .models import GameRecord, JobRecord, JobState
from .schema import build_evidence, normalize_play
from .state_machine import transition
from .store import JsonJobStore


class PostgamePipeline:
    """V0 autonomous pipeline.

    Real paid/compute-heavy services are not called yet. Each stage writes a
    durable artifact contract so later providers can be plugged in without
    redesigning orchestration.
    """

    def __init__(self, store: JsonJobStore, game_provider: Any, data_provider: Any | None = None):
        self.store = store
        self.game_provider = game_provider
        self.data_provider = data_provider or game_provider

    def scan_for_final_games(self) -> list[JobRecord]:
        created: list[JobRecord] = []
        for game in self.game_provider.list_games():
            if not game.is_final or self.store.for_game(game.game_id):
                continue
            stable = uuid.uuid5(uuid.NAMESPACE_URL, f"postgame-video:{game.game_id}")
            job = JobRecord(job_id=str(stable), game=game)
            self.store.save(job)
            created.append(job)
        return created

    def run_until_blocked(self, job: JobRecord) -> JobRecord:
        while job.state not in {JobState.READY_FOR_APPROVAL, JobState.PUBLISHED, JobState.FAILED}:
            self.run_one_stage(job)
        return job

    def _record_attempt(self, job: JobRecord, name: str) -> None:
        job.stage_attempts[name] = job.stage_attempts.get(name, 0) + 1

    @staticmethod
    def _fingerprint(value: Any) -> str:
        raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def run_one_stage(self, job: JobRecord) -> None:
        state = job.state
        try:
            if state == JobState.DETECTED:
                self._record_attempt(job, "ingest")
                transition(job, JobState.INGESTING)
                self.store.save(job)
                data = self.data_provider.ingest_game(job.game)
                if not data.get("play_count"):
                    raise RuntimeError("ingestion produced zero plays")
                normalized = [
                    normalize_play(raw, fallback_game_id=job.game.game_id, source=str(data.get("source", "unknown")))
                    for raw in data["plays"]
                ]
                evidence = [build_evidence(play) for play in normalized]
                data["normalized_plays"] = [play.to_dict() for play in normalized]
                data["evidence_index"] = [item.to_dict() for item in evidence]
                data["fingerprint"] = self._fingerprint(data)
                job.artifacts["game_data"] = data
                transition(job, JobState.DATA_READY)

            elif state == JobState.DATA_READY:
                self._record_attempt(job, "analysis")
                transition(job, JobState.ANALYZING)
                self.store.save(job)
                normalized = [
                    normalize_play(
                        raw,
                        fallback_game_id=job.game.game_id,
                        source=str(job.artifacts["game_data"].get("source", "unknown")),
                    )
                    for raw in job.artifacts["game_data"]["plays"]
                ]
                job.artifacts["analytics"] = build_game_analytics(normalized)
                job.artifacts["analysis_manifest"] = self._build_analysis_manifest(job)
                transition(job, JobState.ANALYSIS_READY)

            elif state == JobState.ANALYSIS_READY:
                self._record_attempt(job, "script")
                transition(job, JobState.SCRIPTING)
                self.store.save(job)
                job.artifacts["script_manifest"] = self._build_script_manifest(job)
                transition(job, JobState.SCRIPT_READY)

            elif state == JobState.SCRIPT_READY:
                self._record_attempt(job, "media_match")
                transition(job, JobState.MEDIA_MATCHING)
                self.store.save(job)
                job.artifacts["media_manifest"] = self._build_media_manifest(job)
                transition(job, JobState.MEDIA_READY)

            elif state == JobState.MEDIA_READY:
                self._record_attempt(job, "render")
                transition(job, JobState.RENDERING)
                self.store.save(job)
                job.artifacts["render_manifest"] = self._build_render_manifest(job)
                transition(job, JobState.QA)

            elif state == JobState.QA:
                self._record_attempt(job, "qa")
                qa = self._run_qa(job)
                job.artifacts["qa_report"] = qa
                if not qa["pass"]:
                    raise RuntimeError("quality gate failed: " + ", ".join(qa["failures"]))
                transition(job, JobState.READY_FOR_APPROVAL)

            else:
                raise RuntimeError(f"no V0 stage handler for state {state.value}")

            self.store.save(job)

        except Exception as exc:
            job.errors.append({"state": state.value, "error": str(exc)})
            if job.state != JobState.FAILED:
                transition(job, JobState.FAILED)
            self.store.save(job)
            raise

    def approve(self, job: JobRecord) -> None:
        if job.state != JobState.READY_FOR_APPROVAL:
            raise RuntimeError("job is not ready for approval")
        transition(job, JobState.PUBLISHED)
        self.store.save(job)

    def _build_analysis_manifest(self, job: JobRecord) -> dict[str, Any]:
        return {
            "status": "CONTRACT_READY",
            "agents": [
                "offensive_scheme",
                "defensive_scheme",
                "advanced_analytics",
                "personnel_matchups",
                "coaching_adjustments",
                "film_evidence_verifier",
                "statistical_verifier",
                "head_coach_reconciler",
            ],
            "evidence_rule": "important factual claims require one or more evidence references",
            "game_data_fingerprint": job.artifacts["game_data"]["fingerprint"],
        }

    def _build_script_manifest(self, job: JobRecord) -> dict[str, Any]:
        return {
            "status": "CONTRACT_READY",
            "mode": "analysis_first",
            "required_fields": ["narration", "claims", "evidence_ids", "visual_instructions"],
            "uncertainty_policy": "do not state uncertain scheme diagnosis as fact",
        }

    def _build_media_manifest(self, job: JobRecord) -> dict[str, Any]:
        return {
            "status": "AWAITING_REAL_FOOTAGE_PROVIDER",
            "rights_gate_required": True,
            "video_search_candidates": ["gemini_video", "twelvelabs"],
            "match_output": ["clip_start_sec", "clip_end_sec", "claim_id", "confidence"],
        }

    def _build_render_manifest(self, job: JobRecord) -> dict[str, Any]:
        return {
            "status": "DRY_RUN_ONLY",
            "renderer": "programmable",
            "planned_layers": ["game_clip", "telestration", "analytics_graphic", "voiceover", "captions"],
        }

    def _run_qa(self, job: JobRecord) -> dict[str, Any]:
        required = ["game_data", "analytics", "analysis_manifest", "script_manifest", "media_manifest", "render_manifest"]
        failures = [f"missing {name}" for name in required if name not in job.artifacts]
        if job.artifacts.get("media_manifest", {}).get("rights_gate_required") is not True:
            failures.append("rights gate missing")
        return {
            "pass": not failures,
            "failures": failures,
            "note": "V0 validates orchestration/contracts only; rendered-video QA is added after footage/render integration.",
        }
