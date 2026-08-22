"""What every eval suite shares: a client, provenance, and the results file shape.

A results file is evidence only if it says what produced it. ``provenance``
records the provider and model the run went through, the model the provider
reported serving, the prompt version, the tool version and git commit, and
the date. ``tests/test_evals.py`` refuses a results file missing any of
those. A suite that could not be run writes ``status: not_run`` with the
reason and no numbers at all, which is the only honest shape for a number
that does not exist.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "evals" / "results"
FIXTURES = ROOT / "tests" / "fixtures"

sys.path.insert(0, str(ROOT / "src"))

from oscal_validate import __version__  # noqa: E402
from oscal_validate.ai import PROMPT_VERSION  # noqa: E402
from oscal_validate.ai.client import (  # noqa: E402
    CassetteClient,
    ModelClient,
    ModelError,
    build_client,
)

REQUIRED_PROVENANCE = (
    "suite",
    "status",
    "date",
    "tool_version",
    "commit",
    "provider",
    "model",
    "served_model",
    "prompt_version",
)


def commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False, cwd=ROOT
    )
    return result.stdout.strip() or "unknown"


def client_from_env(cassette: Path | None = None, replay: bool = False) -> ModelClient:
    """The client the environment selects.

    With a cassette, misses are recorded through the live client, so a run
    can be resumed and later replayed; with ``replay`` as well, no live
    client is built and a miss is an error, so the run touches no network.
    """
    env = dict(os.environ)
    if cassette is not None:
        env["OSCAL_VALIDATE_AI_CASSETTE"] = str(cassette)
        env["OSCAL_VALIDATE_AI_RECORD"] = "0" if replay else "1"
    return build_client(env)


def provenance(
    suite: str, client: ModelClient, served_model: str | None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "suite": suite,
        "status": "run",
        "date": dt.date.today().isoformat(),
        "tool_version": __version__,
        "commit": commit(),
        "provider": client.settings.provider,
        "model": client.settings.model,
        "served_model": served_model or "",
        "prompt_version": PROMPT_VERSION,
        "replayed_from_cassette": isinstance(client, CassetteClient),
    }
    base.update(extra or {})
    return base


def not_run(suite: str, reason: str) -> dict[str, Any]:
    return {
        "provenance": {
            "suite": suite,
            "status": "not_run",
            "date": dt.date.today().isoformat(),
            "tool_version": __version__,
            "commit": commit(),
            "provider": "",
            "model": "",
            "served_model": "",
            "prompt_version": PROMPT_VERSION,
            "reason": reason,
        },
        "summary": {},
        "cases": [],
    }


def write_results(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            cases.append(json.loads(stripped))
    return cases


__all__ = [
    "FIXTURES",
    "REQUIRED_PROVENANCE",
    "RESULTS",
    "ROOT",
    "ModelClient",
    "ModelError",
    "client_from_env",
    "commit",
    "load_cases",
    "not_run",
    "provenance",
    "write_results",
]
