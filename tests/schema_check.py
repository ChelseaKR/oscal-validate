"""A JSON Schema checker small enough to read, that cannot pass by ignoring.

The report schema is validated on the default path, where this project has no
runtime dependency and the test suite adds none for it. So the check is
written here, over the subset of draft 2020-12 that ``report.schema.json``
actually uses.

The dangerous way to write this is the obvious way: walk the schema, handle
the keywords you recognise, and skip the rest. That checker reports no error
for ``{"type": "integer", "minimum": 0}`` if it never implemented ``minimum``,
and it reports no error at all for a keyword added to the schema later. It is
a gate that cannot fail on the half of the contract it does not know about.

So :func:`check` raises :class:`UnsupportedKeyword` on any keyword it does not
implement, rather than passing over it. Adding a keyword to the schema without
teaching this file about it turns the suite red, which is the intended
pressure: the schema stays inside the subset that is actually enforced.
"""

from __future__ import annotations

from typing import Any

#: Keywords that carry no constraint and are ignored on purpose.
ANNOTATIONS = frozenset({"$schema", "$id", "title", "description", "$defs", "examples"})

#: Keywords this checker implements.
IMPLEMENTED = frozenset(
    {"type", "required", "properties", "additionalProperties", "items", "enum", "const", "minimum"}
)

TYPES: dict[str, type | tuple[type, ...]] = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


class UnsupportedKeyword(Exception):
    """The schema uses a keyword this checker does not enforce."""


def _resolve(reference: str, root: dict[str, Any]) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise UnsupportedKeyword(f"$ref {reference!r}: only local pointers are supported")
    node: Any = root
    for segment in reference[2:].split("/"):
        node = node[segment]
    if not isinstance(node, dict):
        raise UnsupportedKeyword(f"$ref {reference!r} does not name a schema")
    return node


def _type_error(schema: dict[str, Any], instance: Any, where: str) -> list[str]:
    declared = schema["type"]
    expected = TYPES.get(declared)
    if expected is None:
        raise UnsupportedKeyword(f"type {declared!r}")
    # bool is a subclass of int in Python; JSON Schema does not agree.
    if isinstance(instance, bool) and declared in ("integer", "number"):
        return [f"{where}: expected {declared}, got boolean"]
    if not isinstance(instance, expected):
        return [f"{where}: expected {declared}, got {type(instance).__name__}"]
    return []


def _check_scalar(instance: Any, schema: dict[str, Any], where: str) -> list[str]:
    errors: list[str] = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{where}: expected {schema['const']!r}, got {instance!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{where}: {instance!r} is not one of {schema['enum']}")
    if "minimum" in schema and isinstance(instance, int | float) and instance < schema["minimum"]:
        errors.append(f"{where}: {instance} is below the minimum {schema['minimum']}")
    return errors


def _check_object(
    instance: dict[str, Any], schema: dict[str, Any], root: dict[str, Any], where: str
) -> list[str]:
    errors: list[str] = []
    properties = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in instance:
            errors.append(f"{where}: required property {name!r} is absent")
    if "additionalProperties" in schema:
        if schema["additionalProperties"] is not False:
            raise UnsupportedKeyword("additionalProperties other than false")
        errors += [
            f"{where}: property {name!r} is not declared"
            for name in instance
            if name not in properties
        ]
    for name, subschema in properties.items():
        if name in instance:
            errors += check(instance[name], subschema, root, f"{where}.{name}")
    return errors


def check(
    instance: Any,
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
    where: str = "$",
) -> list[str]:
    """Every way ``instance`` fails ``schema``. Empty means it conforms."""
    root = schema if root is None else root
    if "$ref" in schema:
        if set(schema) - {"$ref"}:
            raise UnsupportedKeyword("$ref alongside other keywords")
        return check(instance, _resolve(schema["$ref"], root), root, where)

    unknown = set(schema) - ANNOTATIONS - IMPLEMENTED
    if unknown:
        raise UnsupportedKeyword(f"{where}: {', '.join(sorted(unknown))}")

    if "type" in schema:
        mismatch = _type_error(schema, instance, where)
        if mismatch:
            return mismatch

    errors = _check_scalar(instance, schema, where)
    if isinstance(instance, dict):
        errors += _check_object(instance, schema, root, where)
    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors += check(item, schema["items"], root, f"{where}[{index}]")
    return errors
