"""The model client: settings from the environment only, cassettes that replay."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from oscal_validate.ai.client import (
    DEFAULT_BEDROCK_MODEL,
    DEFAULT_MODEL,
    CassetteClient,
    ModelError,
    ScriptedClient,
    build_client,
    prompt_key,
    settings_from_env,
)


def test_default_settings_are_the_claude_api_and_sonnet_5() -> None:
    settings = settings_from_env({})
    assert settings.provider == "anthropic"
    assert settings.model == DEFAULT_MODEL == "claude-sonnet-5"
    assert settings.label == "anthropic:claude-sonnet-5"


def test_bedrock_needs_a_region_and_takes_its_own_default_model() -> None:
    with pytest.raises(ModelError, match="AWS_REGION"):
        settings_from_env({"OSCAL_VALIDATE_AI_PROVIDER": "bedrock"})
    settings = settings_from_env(
        {"OSCAL_VALIDATE_AI_PROVIDER": "bedrock", "AWS_DEFAULT_REGION": "us-east-1"}
    )
    assert settings.model == DEFAULT_BEDROCK_MODEL == "global.anthropic.claude-sonnet-4-6"
    assert settings.region == "us-east-1"


def test_the_two_provider_defaults_are_deliberately_different_models() -> None:
    """A tidy-up that makes the Bedrock default track the API default is a bug.

    ``DEFAULT_MODEL`` is what a third-party deployer with ordinary Claude API
    access should get, and Sonnet 5 is the right answer there. The Bedrock
    default is a separate question, because Bedrock grants model access per
    account: on the account that produced every recorded eval and cassette in
    this repository, ``InvokeModel`` on a Sonnet 5 Bedrock id returns 403
    ``AccessDeniedException`` while Bedrock's entitlement API simultaneously
    reports the model AUTHORIZED. Only the invocation is evidence.

    Two assertions rather than one comparison: pinning both literals means the
    edit that "unifies" them fails here with the reason attached, and it also
    fails if someone advances one of them without deciding about the other.
    """
    assert DEFAULT_MODEL == "claude-sonnet-5"
    assert DEFAULT_BEDROCK_MODEL == "global.anthropic.claude-sonnet-4-6"
    assert not DEFAULT_BEDROCK_MODEL.endswith(DEFAULT_MODEL)


def test_the_model_is_configurable_and_the_provider_is_validated() -> None:
    settings = settings_from_env({"OSCAL_VALIDATE_AI_MODEL": "claude-opus-5"})
    assert settings.model == "claude-opus-5"
    with pytest.raises(ModelError, match="not one of"):
        settings_from_env({"OSCAL_VALIDATE_AI_PROVIDER": "openai"})


def test_a_cassette_records_through_and_then_replays_without_the_inner_client(
    tmp_path: Path,
) -> None:
    path = tmp_path / "cassette.json"
    inner = ScriptedClient(["first answer"])
    recording = CassetteClient(path, inner=inner)
    first = recording.complete("sys", "user")
    assert first.text == "first answer"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert list(stored) == [prompt_key("sys", "user")]

    replay = CassetteClient(path)
    assert replay.complete("sys", "user").text == "first answer"
    # Replay reports where the recordings came from, marked as a replay.
    assert replay.settings.provider == "scripted (replayed)"
    assert replay.settings.model == "scripted"
    assert CassetteClient(tmp_path / "missing.json").settings.provider == "cassette"
    with pytest.raises(ModelError, match="no recorded completion"):
        replay.complete("sys", "a different question")


def test_a_prompt_change_misses_the_cassette() -> None:
    assert prompt_key("a", "b") != prompt_key("a", "b ")


def test_the_scripted_client_runs_dry_loudly() -> None:
    client = ScriptedClient([])
    with pytest.raises(ModelError, match="no answers left"):
        client.complete("s", "u")


def test_build_client_prefers_a_replay_cassette_and_touches_no_sdk(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    path.write_text("{}", encoding="utf-8")
    client = build_client({"OSCAL_VALIDATE_AI_CASSETTE": str(path)})
    assert isinstance(client, CassetteClient)
