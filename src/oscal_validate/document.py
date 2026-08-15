"""Walk an OSCAL document alongside the vendored schema.

This is the one place that decides what a value in an OSCAL document *is*. The
tool does not recognize a UUID by looking at the property name or by pattern
matching every string: it walks the instance next to NIST's published schema
and records, for each scalar it reaches, which OSCAL datatype the schema
declares there and what the schema says that field is for. Every later check
reads this record rather than re-deciding.

Where the schema uses a construct this walk does not resolve, the subtree is
left unwalked and recorded as such. That is the difference between "checked and
clean" and "not looked at", and the two are never merged: an unwalked subtree
becomes an UNVERIFIABLE finding, not silence.

This is deliberately not a JSON Schema implementation. See the README's
"Limits" section for the keywords it does not evaluate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .schema import JsonObject, Resolved, SchemaIndex

#: Refuse rather than partially read a document nested past this depth. A real
#: OSCAL catalog nests perhaps 20 levels; 200 is a hostile-input guard, not a
#: limit anyone should meet.
MAX_DEPTH = 200


class DocumentError(ValueError):
    """The input is not a shape this tool knows how to read."""


def _json_type_of(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if value is None:
        return "null"
    return "string"


def _is_json_type(value: Any, declared: str) -> bool:
    """Whether a scalar matches the JSON type the schema declares for it."""
    found = _json_type_of(value)
    if declared == "number":
        return found in ("integer", "number")
    return found == declared


def escape(token: str) -> str:
    """RFC 6901 JSON Pointer token escaping."""
    return token.replace("~", "~0").replace("/", "~1")


@dataclass(frozen=True)
class Scalar:
    """A scalar value, with the schema's own account of what it is."""

    pointer: str
    name: str
    value: Any
    datatype: str | None
    title: str
    description: str
    enums: tuple[tuple[Any, ...], ...] = ()


@dataclass(frozen=True)
class Note:
    """Something structural the walk observed at one location."""

    pointer: str
    name: str
    detail: str


@dataclass
class Walked:
    model: str
    root: Any
    scalars: list[Scalar] = field(default_factory=list)
    missing: list[Note] = field(default_factory=list)
    undeclared: list[Note] = field(default_factory=list)
    unwalked: list[Note] = field(default_factory=list)
    mistyped: list[Note] = field(default_factory=list)
    no_branch: list[Note] = field(default_factory=list)

    def scalars_named(self, name: str) -> list[Scalar]:
        return [s for s in self.scalars if s.name == name]


def detect_model(data: Any, schema: SchemaIndex) -> tuple[str, JsonObject]:
    """Identify which OSCAL model the document claims to be.

    The schema's top-level ``oneOf`` gives each model exactly one root property
    and forbids any other, so a conforming document has exactly one.
    """
    if not isinstance(data, dict):
        raise DocumentError(
            "expected a JSON object whose single root property names an OSCAL model "
            f"({', '.join(schema.model_names())})"
        )
    roots = [key for key in data if key in schema.models]
    others = [key for key in data if key not in schema.models and key != "$schema"]
    if not roots:
        raise DocumentError(
            "no OSCAL model root found. Expected one of: "
            f"{', '.join(schema.model_names())}. Found: "
            f"{', '.join(sorted(data)) or '(empty object)'}"
        )
    if len(roots) > 1:
        raise DocumentError(
            f"more than one OSCAL model root present ({', '.join(sorted(roots))}). "
            "The schema permits exactly one per document."
        )
    if others:
        raise DocumentError(
            f"unexpected top-level properties beside the {roots[0]} root: "
            f"{', '.join(sorted(others))}"
        )
    return roots[0], schema.models[roots[0]]


class _Walker:
    def __init__(self, schema: SchemaIndex, result: Walked) -> None:
        self.schema = schema
        self.result = result

    def walk(self, instance: Any, node: JsonObject, pointer: str, name: str, depth: int) -> None:
        if depth > MAX_DEPTH:
            raise DocumentError(
                f"{pointer}: document nests deeper than {MAX_DEPTH} levels and was not read further"
            )
        resolved = self.schema.resolve(node)
        if resolved.unresolved is not None:
            self.result.unwalked.append(Note(pointer, name, resolved.unresolved))
            return
        if resolved.branches:
            self._walk_branches(instance, resolved.branches, pointer, name, depth)
            return

        if resolved.datatype is not None:
            self._scalar(instance, resolved, pointer, name)
            return

        declared = resolved.node.get("type")
        if isinstance(instance, dict):
            if declared not in (None, "object"):
                self._mistyped(pointer, name, declared, "an object")
                return
            self._walk_object(instance, resolved.node, pointer, depth)
        elif isinstance(instance, list):
            self._walk_array(instance, resolved.node, pointer, name, declared, depth)
        else:
            self._scalar(instance, resolved, pointer, name)

    def _walk_array(
        self,
        instance: list[Any],
        node: JsonObject,
        pointer: str,
        name: str,
        declared: Any,
        depth: int,
    ) -> None:
        if declared not in (None, "array"):
            self._mistyped(pointer, name, declared, "an array")
            return
        items = node.get("items")
        if not isinstance(items, dict):
            self.result.unwalked.append(
                Note(pointer, name, "the schema declares no item shape for this array")
            )
            return
        for index, element in enumerate(instance):
            self.walk(element, items, f"{pointer}/{index}", name, depth + 1)

    def _scalar(self, instance: Any, resolved: Resolved, pointer: str, name: str) -> None:
        """Record a value at a position the schema declares as a scalar datatype."""
        datatype = resolved.datatype
        declared = datatype.json_type if datatype is not None else None
        if isinstance(instance, dict | list):
            self._mistyped(
                pointer, name, declared, "an object" if isinstance(instance, dict) else "an array"
            )
            return
        if declared is not None and not _is_json_type(instance, declared):
            self._mistyped(pointer, name, declared, f"a JSON {_json_type_of(instance)}")
            return
        self.result.scalars.append(
            Scalar(
                pointer=pointer,
                name=name,
                value=instance,
                datatype=datatype.name if datatype is not None else None,
                title=resolved.title,
                description=resolved.description,
                enums=resolved.enums,
            )
        )

    def _mistyped(self, pointer: str, name: str, declared: Any, found: str) -> None:
        # The quoting matters: structure.py reads the declared type back out of
        # this message to build the finding's citation.
        expected = str(declared) if declared is not None else "scalar"
        self.result.mistyped.append(
            Note(
                pointer,
                name,
                f"the schema declares type {expected!r} here, and the value is {found}",
            )
        )

    def _walk_object(
        self, instance: JsonObject, node: JsonObject, pointer: str, depth: int
    ) -> None:
        properties = node.get("properties")
        properties = properties if isinstance(properties, dict) else {}
        required = node.get("required")
        required = [str(r) for r in required] if isinstance(required, list) else []
        closed = node.get("additionalProperties") is False
        assembly = str(node.get("title", "")) or "this object"

        for name in required:
            if name not in instance:
                self.result.missing.append(Note(pointer, name, assembly))
        for key in instance:
            child = properties.get(key)
            if not isinstance(child, dict):
                if closed:
                    self.result.undeclared.append(Note(pointer, str(key), assembly))
                continue
            self.walk(instance[key], child, f"{pointer}/{escape(str(key))}", str(key), depth + 1)

    def _walk_branches(
        self,
        instance: Any,
        branches: tuple[JsonObject, ...],
        pointer: str,
        name: str,
        depth: int,
    ) -> None:
        if not isinstance(instance, dict):
            self.result.unwalked.append(
                Note(
                    pointer,
                    name,
                    "the schema offers object alternatives and the value is not an object",
                )
            )
            return
        matching = [b for b in branches if _accepts(b, instance)]
        if not matching:
            self.result.no_branch.append(
                Note(pointer, name, _describe_branches(branches, instance))
            )
            return
        if len(matching) > 1 and not _agree_on(matching, instance):
            self.result.unwalked.append(
                Note(
                    pointer,
                    name,
                    "more than one alternative in the schema accepts this object and they "
                    "disagree about what its properties mean, so it was not read further",
                )
            )
            return
        self._walk_object(instance, matching[0], pointer, depth)


def _accepts(branch: JsonObject, instance: JsonObject) -> bool:
    """True when this alternative could describe the object as written."""
    properties = branch.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = branch.get("required")
    required = [str(r) for r in required] if isinstance(required, list) else []
    if any(name not in instance for name in required):
        return False
    if branch.get("additionalProperties") is False:
        return all(key in properties for key in instance)
    return True


def _agree_on(branches: list[JsonObject], instance: JsonObject) -> bool:
    """True when every matching alternative says the same thing about this object.

    Where the alternatives differ only in properties the object does not use,
    reading it under any one of them gives identical results, so descending is
    a deduction rather than a choice.
    """
    first, rest = branches[0], branches[1:]
    if any(_required_of(b) != _required_of(first) for b in rest):
        return False
    for key in instance:
        shapes = {_canonical(b.get("properties", {}).get(key)) for b in branches}
        if len(shapes) != 1:
            return False
    return True


def _required_of(branch: JsonObject) -> frozenset[str]:
    required = branch.get("required")
    return frozenset(str(r) for r in required) if isinstance(required, list) else frozenset()


def _canonical(node: Any) -> str:
    return json.dumps(node, sort_keys=True)


def _describe_branches(branches: tuple[JsonObject, ...], instance: JsonObject) -> str:
    parts = []
    for branch in branches:
        required = sorted(_required_of(branch))
        allowed = sorted(branch.get("properties", {})) if branch.get("properties") else []
        clause = f"requires {required}" if required else "requires nothing"
        if branch.get("additionalProperties") is False:
            clause += f" and permits only {allowed}"
        parts.append(clause)
    return (
        f"the object has properties {sorted(instance)}, and no alternative accepts it: "
        + "; ".join(f"alternative {i + 1} {p}" for i, p in enumerate(parts))
    )


def walk_document(data: Any, schema: SchemaIndex) -> Walked:
    """Walk a decoded OSCAL document beside the vendored schema."""
    model, root_schema = detect_model(data, schema)
    result = Walked(model=model, root=data[model])
    _Walker(schema, result).walk(data[model], root_schema, f"/{escape(model)}", model, 0)
    return result
