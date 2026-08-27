"""Load and index the vendored OSCAL JSON Schema snapshot.

Everything this tool knows about OSCAL comes from one file: NIST's published
``oscal_complete_schema.json``, vendored unmodified under ``vendor/oscal/``
with its source URL, retrieval date, and SHA-256 recorded in
``vendor/SOURCES.md`` and enforced by ``tests/test_vendor_integrity.py``.
There is no hand-written model of OSCAL in this repository: the model roots,
the required-property lists, the datatype patterns, and even the wording that
separates an identifier from an identifier *reference* are all read out of the
snapshot at load time.

The schema is JSON Schema draft-07. This module does not implement draft-07.
It implements the subset the OSCAL schema actually uses for structure --
``$ref``, ``properties``, ``required``, ``additionalProperties``, ``items``,
``type``, ``pattern``, ``minItems``, ``minimum``, and the ``anyOf``/``allOf``
shapes NIST uses -- and it reports what it could not resolve rather than
guessing. See the README's "Limits" section for the keywords it deliberately
does not evaluate.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any

#: Definition names that hold OSCAL's scalar datatypes, e.g. ``UUIDDatatype``.
_DATATYPE_NAME = re.compile(r"^[A-Za-z0-9]+Datatype$")

VENDORED_SCHEMA = "oscal/complete_schema.json"

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class Datatype:
    """One of OSCAL's scalar datatypes, as the vendored schema declares it."""

    name: str
    description: str
    json_type: str | None
    pattern: str | None
    #: The lowest value the schema permits, where it declares one. OSCAL's two
    #: bounded integer datatypes are the only places it does.
    minimum: float | None = None

    @property
    def compiled(self) -> re.Pattern[str] | None:
        return _compile(self.pattern) if self.pattern is not None else None


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str] | None:
    """Compile a schema pattern, or None where Python cannot express it.

    OSCAL's ``TokenDatatype`` pattern uses ``\\p{L}`` and ``\\p{N}`` Unicode
    property escapes, which ECMA-262 supports and Python's ``re`` does not.
    Returning None there is the honest outcome: a pattern this tool cannot
    compile is one it must not pretend to have checked.
    """
    try:
        return re.compile(pattern)
    except re.error:
        return None


@dataclass(frozen=True)
class Resolved:
    """A schema node with ``$ref`` chains followed and scalar unions flattened.

    ``datatype`` is set when the node ultimately refers to one of OSCAL's
    scalar datatypes. ``enums`` holds the literal value sets that sit beside a
    datatype in an ``anyOf``; they are consulted only to *suppress* a pattern
    finding, never to raise one (see the README's "Limits").
    """

    node: JsonObject
    datatype: Datatype | None
    title: str
    description: str
    enums: tuple[tuple[Any, ...], ...] = ()
    #: Object alternatives from an ``anyOf`` whose branches declare properties.
    branches: tuple[JsonObject, ...] = ()
    #: The two nodes of an ``anyOf`` that offers one object or an array of the
    #: same object, in that order. See ``_one_or_many``.
    one_or_many: tuple[JsonObject, JsonObject] | None = None
    #: Set when the node uses a construct this module does not resolve.
    unresolved: str | None = None
    #: The last named definition followed, without its module prefix, e.g.
    #: ``responsible-party`` for ``oscal-complete-oscal-metadata:responsible-party``.
    definition: str = ""


@dataclass
class SchemaIndex:
    raw: JsonObject
    definitions: JsonObject
    datatypes: dict[str, Datatype]
    #: Root property name (``catalog``, ``profile``, ...) -> its root schema.
    models: dict[str, JsonObject] = field(default_factory=dict)

    # -- $ref plumbing ----------------------------------------------------

    def dereference(self, ref: str) -> JsonObject:
        if not ref.startswith("#/definitions/"):
            raise SchemaError(f"unsupported $ref form in the vendored schema: {ref}")
        name = ref[len("#/definitions/") :]
        target = self.definitions.get(name)
        if not isinstance(target, dict):
            raise SchemaError(f"vendored schema has no definition {name}")
        return target

    def datatype_for(self, ref: str) -> Datatype | None:
        name = ref.rsplit("/", 1)[-1]
        return self.datatypes.get(name)

    def resolve(self, node: JsonObject) -> Resolved:
        """Follow ``$ref``/``allOf``/``anyOf`` down to something checkable."""
        title = str(node.get("title", ""))
        description = str(node.get("description", ""))
        datatype: Datatype | None = None
        enums: list[tuple[Any, ...]] = []
        branches: tuple[JsonObject, ...] = ()
        one_or_many: tuple[JsonObject, JsonObject] | None = None
        unresolved: str | None = None
        definition = ""
        current = node

        for _ in range(_MAX_REF_DEPTH):
            ref = current.get("$ref")
            if isinstance(ref, str):
                found = self.datatype_for(ref)
                if found is not None:
                    datatype = found
                    break
                definition = ref.rsplit("/", 1)[-1].rsplit(":", 1)[-1]
                current = self.dereference(ref)
                title = title or str(current.get("title", ""))
                description = description or str(current.get("description", ""))
                continue

            union = current.get("allOf") or current.get("anyOf")
            if isinstance(union, list) and union:
                if all(isinstance(b, dict) and "properties" in b for b in union):
                    branches = tuple(union)
                    break
                pair = _one_or_many(current)
                if pair is not None:
                    one_or_many = pair
                    break
                collapsed = self._collapse_scalar_union(union, enums)
                if collapsed is None:
                    unresolved = (
                        "the schema combines alternatives here in a form this tool does not resolve"
                    )
                    break
                current = collapsed
                continue
            break
        else:  # pragma: no cover - a cycle would need a malformed snapshot
            raise SchemaError("$ref chain in the vendored schema did not terminate")

        return Resolved(
            node=current,
            datatype=datatype,
            title=title,
            description=description,
            enums=tuple(enums),
            branches=branches,
            one_or_many=one_or_many,
            unresolved=unresolved,
            definition=definition,
        )

    def _collapse_scalar_union(
        self, union: list[Any], enums: list[tuple[Any, ...]]
    ) -> JsonObject | None:
        """Reduce a scalar ``allOf``/``anyOf`` to the one constraining branch.

        OSCAL writes scalar unions in exactly two shapes: a datatype ``$ref``
        beside an ``enum``, and a datatype ``$ref`` beside an extra keyword such
        as ``minimum``. Both have one branch that names the datatype; the enums
        are carried along. Anything else returns None and is reported.
        """
        constraining = [b for b in union if isinstance(b, dict) and "enum" not in b]
        for branch in union:
            if isinstance(branch, dict) and isinstance(branch.get("enum"), list):
                enums.append(tuple(branch["enum"]))
        if len(constraining) != 1:
            return None
        return constraining[0]

    # -- models -----------------------------------------------------------

    def model_names(self) -> tuple[str, ...]:
        return tuple(sorted(self.models))


_MAX_REF_DEPTH = 16


class SchemaError(RuntimeError):
    """The vendored schema is not the shape this module knows how to read."""


def _read_vendor(relpath: str) -> Any:
    path = resources.files("oscal_validate").joinpath("vendor").joinpath(relpath)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _one_or_many(node: JsonObject) -> tuple[JsonObject, JsonObject] | None:
    """The two nodes of "one X, or an array of X", where the schema writes it.

    OSCAL 1.2.3 writes this shape once, at
    ``oscal-complete-oscal-mapping:mapping-collection/properties/mappings``:

        {"anyOf": [{"$ref": X},
                   {"type": "array", "minItems": 1, "items": {"$ref": X}}]}

    Every other repeatable assembly in the schema is a plain array, because
    every other ``group-as`` in the vendored metaschema modules carries
    ``in-json="ARRAY"`` and the one at ``mappings`` does not.

    Nothing is interpreted here. ``anyOf`` requires the instance to satisfy at
    least one branch; the two branches name the same definition, and one of
    them requires an array. So a JSON array can only be the array branch and a
    JSON object can only be the other, and the schema decides which applies
    without this tool choosing anything. The pair is returned only when both
    branches carry the identical ``$ref``: two different targets would be a
    real choice between alternatives, and this function declines it.
    """
    union = node.get("anyOf")
    if not isinstance(union, list) or len(union) != 2:
        return None
    single, array = union
    if not (isinstance(single, dict) and isinstance(array, dict)):
        return None
    if set(single) != {"$ref"} or array.get("type") != "array":
        single, array = array, single
    if set(single) != {"$ref"} or array.get("type") != "array":
        return None
    items = array.get("items")
    if not isinstance(items, dict) or set(items) != {"$ref"}:
        return None
    if items["$ref"] != single["$ref"]:
        return None
    return (single, array)


def _referenced(branch: JsonObject, definitions: JsonObject) -> JsonObject:
    """The definition an ``allOf`` branch refers to, or an empty node."""
    ref = branch.get("$ref")
    target = definitions.get(ref.rsplit("/", 1)[-1]) if isinstance(ref, str) else None
    return target if isinstance(target, dict) else {}


def _narrower(declared: Any, base: Any) -> str | None:
    """The narrower of the two JSON types one ``allOf`` conjunction states.

    An ``allOf`` requires every branch at once, so where a branch widens what
    the referenced base datatype declares, the conjunction is still the base's.
    OSCAL does this twice, in ``PositiveIntegerDatatype`` and
    ``NonNegativeIntegerDatatype``: each is a ``$ref`` to ``IntegerDatatype``
    beside a branch declaring ``"type": "number"``. Reading only the branch
    loses the integer requirement, and a fractional port number then passes.
    """
    if "integer" in (declared, base):
        return "integer"
    if isinstance(declared, str):
        return declared
    return base if isinstance(base, str) else None


def _index_datatypes(definitions: JsonObject) -> dict[str, Datatype]:
    datatypes: dict[str, Datatype] = {}
    for name, node in definitions.items():
        if not _DATATYPE_NAME.match(name) or not isinstance(node, dict):
            continue
        pattern = node.get("pattern")
        json_type = node.get("type")
        minimum = node.get("minimum")
        for branch in node.get("allOf", []):
            if not isinstance(branch, dict):  # pragma: no cover - hash-checked snapshot
                continue
            base = _referenced(branch, definitions)
            # Deliberately not widened to the referenced base's pattern. An
            # allOf conjunction requires both, and the branch's is the specific
            # one: EmailAddressDatatype refs StringDatatype and then declares
            # the email pattern beside it.
            pattern = pattern or branch.get("pattern")
            json_type = _narrower(json_type or branch.get("type"), base.get("type"))
            minimum = minimum if minimum is not None else branch.get("minimum")
        datatypes[name] = Datatype(
            name=name,
            description=str(node.get("description", "")),
            json_type=json_type if isinstance(json_type, str) else None,
            pattern=pattern if isinstance(pattern, str) else None,
            minimum=minimum if isinstance(minimum, int | float) else None,
        )
    return datatypes


def _index_models(raw: JsonObject) -> dict[str, JsonObject]:
    """The root models, read from the schema's top-level ``oneOf``.

    Each branch is an object with one OSCAL root property plus the optional
    ``$schema`` directive, so the branch's ``required`` names the model.
    """
    models: dict[str, JsonObject] = {}
    for branch in raw.get("oneOf", []):
        if not isinstance(branch, dict):  # pragma: no cover - hash-checked snapshot
            continue
        required = branch.get("required")
        properties = branch.get("properties")
        if not isinstance(required, list) or not isinstance(properties, dict):
            continue  # pragma: no cover - hash-checked snapshot
        for name in required:
            target = properties.get(name)
            if isinstance(target, dict):
                models[str(name)] = target
    return models


@lru_cache(maxsize=1)
def load_schema() -> SchemaIndex:
    raw = _read_vendor(VENDORED_SCHEMA)
    if not isinstance(raw, dict):  # pragma: no cover - hash-checked snapshot
        raise SchemaError("the vendored schema is not a JSON object")
    definitions = raw.get("definitions")
    if not isinstance(definitions, dict):  # pragma: no cover - hash-checked snapshot
        raise SchemaError("the vendored schema has no definitions")
    index = SchemaIndex(
        raw=raw,
        definitions=definitions,
        datatypes=_index_datatypes(definitions),
    )
    index.models = _index_models(raw)
    return index


def schema_release() -> str:
    """The OSCAL release the vendored snapshot is from, read from its ``$id``.

    The published ``$id`` is
    ``http://csrc.nist.gov/ns/oscal/1.0/<release>/oscal-complete-schema.json``.
    """
    raw = load_schema().raw
    identifier = str(raw.get("$id", ""))
    parts = identifier.rstrip("/").split("/")
    return parts[-2] if len(parts) >= 2 else ""


__all__ = [
    "VENDORED_SCHEMA",
    "Datatype",
    "Resolved",
    "SchemaError",
    "SchemaIndex",
    "load_schema",
    "schema_release",
]
