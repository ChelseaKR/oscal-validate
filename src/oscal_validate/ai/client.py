"""The one place a model is called from.

Three clients share one interface. ``AnthropicClient`` calls the public
``anthropic`` SDK, against the Claude API by default or Amazon Bedrock when
the environment says so; the SDK is imported inside the constructor so that
importing this module costs nothing and needs nothing. ``CassetteClient``
replays recorded completions from a JSON file, keyed by a hash of the exact
prompt, and records through to an inner client when the key is missing; it
is how the command tests run without a network and how an eval run can be
replayed byte for byte. ``ScriptedClient`` answers from a list, for tests.

Credentials come from the environment only (``ANTHROPIC_API_KEY`` or an AWS
credential chain). Nothing here reads a key into a variable, and nothing
here writes one anywhere.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: The default model on the Claude API. Configurable with OSCAL_VALIDATE_AI_MODEL.
DEFAULT_MODEL = "claude-sonnet-5"
#: The same model, as Amazon Bedrock names it.
DEFAULT_BEDROCK_MODEL = "global.anthropic.claude-sonnet-5"
DEFAULT_MAX_TOKENS = 8000

PROVIDERS = ("anthropic", "bedrock")


class ModelError(RuntimeError):
    """A model call failed, in a way the command reports and stops on."""


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    model: str
    region: str | None = None
    max_tokens: int = DEFAULT_MAX_TOKENS

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}"


def settings_from_env(environ: Mapping[str, str] | None = None) -> ModelSettings:
    """Provider and model from the environment, never from a file.

    ``OSCAL_VALIDATE_AI_PROVIDER`` is ``anthropic`` (default) or ``bedrock``;
    ``OSCAL_VALIDATE_AI_MODEL`` overrides the model id; ``AWS_REGION`` (or
    ``AWS_DEFAULT_REGION``) is required for Bedrock and has no default here.
    """
    env = os.environ if environ is None else environ
    provider = env.get("OSCAL_VALIDATE_AI_PROVIDER", "anthropic").strip().lower()
    if provider not in PROVIDERS:
        raise ModelError(
            f"OSCAL_VALIDATE_AI_PROVIDER={provider!r} is not one of {', '.join(PROVIDERS)}"
        )
    default = DEFAULT_MODEL if provider == "anthropic" else DEFAULT_BEDROCK_MODEL
    model = env.get("OSCAL_VALIDATE_AI_MODEL", "").strip() or default
    region = env.get("AWS_REGION", "").strip() or env.get("AWS_DEFAULT_REGION", "").strip()
    if provider == "bedrock" and not region:
        raise ModelError("OSCAL_VALIDATE_AI_PROVIDER=bedrock needs AWS_REGION set")
    return ModelSettings(provider=provider, model=model, region=region or None)


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    stop_reason: str


class ModelClient(Protocol):
    @property
    def settings(self) -> ModelSettings: ...

    def complete(self, system: str, user: str) -> Completion: ...


class AnthropicClient:
    """The public SDK, imported only when a model-backed command runs."""

    def __init__(self, settings: ModelSettings) -> None:
        self._settings = settings
        try:
            import anthropic  # noqa: PLC0415 - lazy on purpose; see the module docstring
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise ModelError(
                "the anthropic SDK is not installed; install it with "
                "pip install 'oscal-validate[ai]'"
            ) from exc
        self._errors = anthropic
        self._client: anthropic.Anthropic | anthropic.AnthropicBedrock = (
            anthropic.AnthropicBedrock(aws_region=settings.region)
            if settings.provider == "bedrock"
            else anthropic.Anthropic()
        )

    @property
    def settings(self) -> ModelSettings:
        return self._settings

    def complete(self, system: str, user: str) -> Completion:
        errors = self._errors
        try:
            response = self._client.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                thinking={"type": "adaptive"},
            )
        except errors.AuthenticationError as exc:
            raise ModelError(f"the model provider rejected the credentials: {exc.message}") from exc
        except errors.PermissionDeniedError as exc:
            raise ModelError(
                f"the model provider refused {self._settings.model}: {exc.message}"
            ) from exc
        except errors.NotFoundError as exc:
            raise ModelError(f"model {self._settings.model} was not found: {exc.message}") from exc
        except errors.RateLimitError as exc:
            raise ModelError(f"rate limited by the model provider: {exc.message}") from exc
        except errors.APIStatusError as exc:
            raise ModelError(f"model provider error {exc.status_code}: {exc.message}") from exc
        except errors.APIConnectionError as exc:
            raise ModelError(f"could not reach the model provider: {exc}") from exc
        except ImportError as exc:  # pragma: no cover - only without the bedrock extra
            raise ModelError(
                f"the {self._settings.provider} provider needs an extra that is not installed "
                f"({exc.name}); install it with pip install 'oscal-validate[bedrock]'"
            ) from exc
        text = "".join(block.text for block in response.content if block.type == "text")
        return Completion(
            text=text,
            model=response.model,
            provider=self._settings.provider,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            stop_reason=response.stop_reason or "",
        )


def prompt_key(system: str, user: str) -> str:
    return hashlib.sha256(f"{system}\x00{user}".encode()).hexdigest()


class CassetteClient:
    """Replay recorded completions; record through an inner client when absent.

    The cassette is a JSON object from prompt key to the recorded completion.
    Keys are a hash of the exact system and user text, so a prompt change
    misses the cassette rather than replaying an answer to a different
    question. With no inner client, a miss is an error naming the key.
    """

    def __init__(
        self,
        path: Path,
        inner: ModelClient | None = None,
        settings: ModelSettings | None = None,
    ) -> None:
        self.path = path
        self._inner = inner
        self._entries: dict[str, dict[str, object]] = (
            json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        )
        self._settings = settings or (
            inner.settings if inner else ModelSettings(provider="cassette", model=path.name)
        )

    @property
    def settings(self) -> ModelSettings:
        return self._settings

    def complete(self, system: str, user: str) -> Completion:
        key = prompt_key(system, user)
        entry = self._entries.get(key)
        if entry is None:
            if self._inner is None:
                raise ModelError(f"no recorded completion for prompt {key[:12]} in {self.path}")
            completion = self._inner.complete(system, user)
            self._entries[key] = {
                "text": completion.text,
                "model": completion.model,
                "provider": completion.provider,
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
                "stop_reason": completion.stop_reason,
            }
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps(self._entries, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return completion
        return Completion(
            text=str(entry["text"]),
            model=str(entry["model"]),
            provider=str(entry["provider"]),
            input_tokens=int(str(entry["input_tokens"])),
            output_tokens=int(str(entry["output_tokens"])),
            stop_reason=str(entry["stop_reason"]),
        )


class ScriptedClient:
    """Answers in order from a list. For tests of everything but the model."""

    def __init__(self, answers: list[str], model: str = "scripted") -> None:
        self._answers = list(answers)
        self._settings = ModelSettings(provider="scripted", model=model)
        self.prompts: list[tuple[str, str]] = []

    @property
    def settings(self) -> ModelSettings:
        return self._settings

    def complete(self, system: str, user: str) -> Completion:
        self.prompts.append((system, user))
        if not self._answers:
            raise ModelError("the scripted client has no answers left")
        return Completion(
            text=self._answers.pop(0),
            model=self._settings.model,
            provider="scripted",
            input_tokens=0,
            output_tokens=0,
            stop_reason="end_turn",
        )


def build_client(environ: Mapping[str, str] | None = None) -> ModelClient:
    """The client a command uses, chosen entirely by the environment.

    ``OSCAL_VALIDATE_AI_CASSETTE`` names a cassette file; with
    ``OSCAL_VALIDATE_AI_RECORD=1`` misses are recorded through the live
    client, otherwise a miss is an error and no network is touched.
    """
    env = os.environ if environ is None else environ
    cassette = env.get("OSCAL_VALIDATE_AI_CASSETTE", "").strip()
    if cassette and env.get("OSCAL_VALIDATE_AI_RECORD", "").strip() != "1":
        return CassetteClient(Path(cassette))
    live = AnthropicClient(settings_from_env(env))
    if cassette:
        return CassetteClient(Path(cassette), inner=live)
    return live
