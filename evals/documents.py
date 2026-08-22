"""The real documents the evals run over, and the defects injected into them.

``cases/documents.json`` names twelve published NIST documents across the
seven models, by URL and SHA-256. They live in ``.survey-cache/`` (the
survey harness's store, not committed) or, for one of them, in
``tests/fixtures/``. A document whose bytes do not match its hash is
refused; one that is absent is recorded as skipped. Nothing is fetched.

Defects are injected by name, deterministically, one at a time, into an
in-memory copy: the same corruptions ``tests/test_break_the_gate.py`` uses
to prove the validator catches them. Each injector returns the corrupted
copy or ``None`` when the document has no place to put that defect, and
the runner records which.
"""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evals.common import FIXTURES, ROOT

CACHE = ROOT / ".survey-cache"
DOCUMENTS = Path(__file__).resolve().parent / "cases" / "documents.json"


@dataclass(frozen=True)
class Document:
    identifier: str
    model: str
    url: str
    sha256: str
    path: Path
    resolve: tuple[Path, ...]

    @property
    def payload(self) -> Any:
        return json.loads(self.path.read_text(encoding="utf-8"))


def _checked(path: Path, sha256: str) -> Path | None:
    if not path.is_file():
        return None
    if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
        raise SystemExit(f"{path} does not match the SHA-256 in documents.json; refusing to use it")
    return path


def load_documents() -> tuple[list[Document], list[dict[str, str]]]:
    """Documents that are present and match, plus a record of each one skipped."""
    manifest = json.loads(DOCUMENTS.read_text(encoding="utf-8"))
    found: list[Document] = []
    skipped: list[dict[str, str]] = []
    for entry in manifest["documents"]:
        path = None
        if entry.get("fixture"):
            path = _checked(FIXTURES / entry["fixture"], entry["sha256"])
        if path is None:
            path = _checked(CACHE / entry["cache"], entry["sha256"])
        if path is None:
            skipped.append({"id": entry["id"], "reason": "not in the local cache"})
            continue
        resolve: list[Path] = []
        for dep in entry.get("resolve", []):
            dep_path = _checked(CACHE / dep["cache"], dep["sha256"])
            if dep_path is None:
                break
            resolve.append(dep_path)
        else:
            found.append(
                Document(
                    entry["id"], entry["model"], entry["url"], entry["sha256"], path, tuple(resolve)
                )
            )
            continue
        skipped.append({"id": entry["id"], "reason": "a --resolve document is not in the cache"})
    return found, skipped


@contextmanager
def materialized(document: Document, payload: Any) -> Iterator[Path]:
    """A corrupted copy on disk under the document's own name, for the validator."""
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / document.path.name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        yield path


# -- injectors ---------------------------------------------------------------

Injector = Callable[[Any], Any | None]


def _root(payload: Any) -> tuple[str, dict[str, Any]]:
    (name, body), *_ = payload.items()
    return name, body


def remove_required(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    _, body = _root(out)
    if "last-modified" not in body.get("metadata", {}):
        return None
    del body["metadata"]["last-modified"]
    return out


def add_undeclared(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    _, body = _root(out)
    body.setdefault("metadata", {})["invented-property"] = "hello"
    return out


def break_uuid(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    _, body = _root(out)
    if "uuid" not in body:
        return None
    body["uuid"] = "not-a-uuid"
    return out


def drop_timezone(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    _, body = _root(out)
    stamp = body.get("metadata", {}).get("last-modified")
    if not isinstance(stamp, str) or not stamp.endswith(("Z", "+00:00")):
        return None
    body["metadata"]["last-modified"] = stamp.removesuffix("Z").removesuffix("+00:00")
    return out


def wrong_type(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    _, body = _root(out)
    if "title" not in body.get("metadata", {}):
        return None
    body["metadata"]["title"] = {"not": "a string"}
    return out


def _uuids(node: Any, path: str = "") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uuid" and isinstance(value, str):
                found.append((path + "/uuid", value))
            found.extend(_uuids(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_uuids(item, f"{path}/{index}"))
    return found


def duplicate_uuid(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    name, body = _root(out)
    root_uuid = body.get("uuid")
    others = [
        (p, v) for p, v in _uuids(body, "/" + name) if v != root_uuid and p != f"/{name}/uuid"
    ]
    if not isinstance(root_uuid, str) or not others:
        return None
    pointer, _ = others[0]
    node = out
    for token in pointer.strip("/").split("/")[:-1]:
        node = node[int(token)] if isinstance(node, list) else node[token]
    node["uuid"] = root_uuid
    return out


def _hrefs(node: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "href" and isinstance(value, str) and value.startswith("#"):
                found.append(path + "/href")
            found.extend(_hrefs(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.extend(_hrefs(item, f"{path}/{index}"))
    return found


def dangle_fragment(payload: Any) -> Any | None:
    out = copy.deepcopy(payload)
    pointers = _hrefs(out)
    if not pointers:
        return None
    node = out
    tokens = pointers[0].strip("/").split("/")
    for token in tokens[:-1]:
        node = node[int(token)] if isinstance(node, list) else node[token]
    node["href"] = "#00000000-0000-4000-8000-000000000000"
    return out


INJECTORS: dict[str, Injector] = {
    "remove_required": remove_required,
    "add_undeclared": add_undeclared,
    "break_uuid": break_uuid,
    "drop_timezone": drop_timezone,
    "wrong_type": wrong_type,
    "duplicate_uuid": duplicate_uuid,
    "dangle_fragment": dangle_fragment,
}
