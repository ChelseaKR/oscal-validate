"""RFC 6901 pointers and the three RFC 6902 operations a repair draft may use.

Written here rather than taken as a dependency so that the repair path has
exactly the semantics it claims: ``add``, ``remove``, and ``replace`` on an
in-memory copy, applied in order, each one failing loudly when its path does
not exist. ``move``, ``copy``, and ``test`` are refused, which keeps a draft
to edits a reader can see in a diff.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

ALLOWED_OPS = ("add", "remove", "replace")


class PatchError(ValueError):
    """A patch that cannot be applied as written; the draft is reported, not shown."""


def unescape(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def split(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"pointer {pointer!r} does not start with '/'")
    return [unescape(token) for token in pointer[1:].split("/")]


def resolve(document: Any, pointer: str) -> Any:
    """The value at a pointer, or PatchError naming the first missing step."""
    node = document
    for token in split(pointer):
        node = _step(node, token, pointer)
    return node


def _step(node: Any, token: str, pointer: str) -> Any:
    if isinstance(node, dict):
        if token not in node:
            raise PatchError(f"{pointer}: no property {token!r}")
        return node[token]
    if isinstance(node, list):
        index = _index(node, token, pointer, allow_end=False)
        return node[index]
    raise PatchError(f"{pointer}: cannot step into a {type(node).__name__} with {token!r}")


def _index(node: list[Any], segment: str, pointer: str, allow_end: bool) -> int:
    if segment == "-" and allow_end:
        return len(node)
    if not segment.isdigit():
        raise PatchError(f"{pointer}: {segment!r} is not an array index")
    index = int(segment)
    limit = len(node) + (1 if allow_end else 0)
    if index >= limit:
        raise PatchError(f"{pointer}: index {index} is past the end of an array of {len(node)}")
    return index


@dataclass(frozen=True)
class Operation:
    op: str
    path: str
    value: Any = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Operation:
        op = str(raw.get("op", ""))
        if op not in ALLOWED_OPS:
            raise PatchError(f"operation {op!r} is not one of {', '.join(ALLOWED_OPS)}")
        path = raw.get("path")
        if not isinstance(path, str):
            raise PatchError("an operation needs a string path")
        if op != "remove" and "value" not in raw:
            raise PatchError(f"{op} at {path} needs a value")
        return cls(op=op, path=path, value=raw.get("value"))

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"op": self.op, "path": self.path}
        if self.op != "remove":
            out["value"] = self.value
        return out


def apply(document: Any, operations: list[Operation]) -> Any:
    """A patched deep copy. The input is never modified."""
    result = copy.deepcopy(document)
    for operation in operations:
        _apply_one(result, operation)
    return result


def _apply_one(document: Any, operation: Operation) -> None:
    tokens = split(operation.path)
    if not tokens:
        raise PatchError("a draft may not replace the whole document")
    parent = resolve(
        document, "/" + "/".join(escape(t) for t in tokens[:-1]) if tokens[:-1] else ""
    )
    last = tokens[-1]
    if isinstance(parent, dict):
        _apply_to_object(parent, last, operation)
    elif isinstance(parent, list):
        _apply_to_array(parent, last, operation)
    else:
        raise PatchError(f"{operation.path}: parent is a {type(parent).__name__}")


def _apply_to_object(parent: dict[str, Any], key: str, operation: Operation) -> None:
    if operation.op == "add":
        parent[key] = copy.deepcopy(operation.value)
        return
    if key not in parent:
        raise PatchError(f"{operation.path}: no property {key!r} to {operation.op}")
    if operation.op == "remove":
        del parent[key]
    else:
        parent[key] = copy.deepcopy(operation.value)


def _apply_to_array(parent: list[Any], key: str, operation: Operation) -> None:
    if operation.op == "add":
        index = _index(parent, key, operation.path, allow_end=True)
        parent.insert(index, copy.deepcopy(operation.value))
        return
    index = _index(parent, key, operation.path, allow_end=False)
    if operation.op == "remove":
        del parent[index]
    else:
        parent[index] = copy.deepcopy(operation.value)


def parent_pointer(pointer: str) -> str:
    tokens = split(pointer)
    return "/" + "/".join(escape(t) for t in tokens[:-1]) if len(tokens) > 1 else ""
