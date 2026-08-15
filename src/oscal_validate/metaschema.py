"""Read NIST's published constraint layer out of the vendored metaschema files.

This is the part of OSCAL that most validation misses, and the reason this
repository exists.

OSCAL's JSON Schema expresses shape and datatypes and nothing else. Checked
against the vendored ``oscal_complete_schema.json`` for OSCAL 1.2.3, it
contains no ``uniqueItems``, no ``const``, no ``if``, no ``not``, and no
``dependentRequired``: it cannot state that two controls must not share an id,
and it cannot state that a link's ``#`` fragment has to name a resource that
exists. Those rules are real and they are published, but they live in the
Metaschema constraint layer that NIST ships alongside the schema, in the
``*_metaschema_RESOLVED.xml`` files vendored here.

This module parses those files and evaluates a bounded subset of the
constraints they declare. The subset is bounded because the constraint targets
are Metapath expressions, and a partial Metapath implementation that guessed at
the expressions it did not understand would be worse than no implementation at
all. So the parser reports, per constraint, whether it was evaluated, and the
validator surfaces the ones it did not evaluate rather than passing over them.

The severity of a constraint finding is the ``level`` NIST declares on the
constraint, not a severity this tool assigns.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any
from xml.etree import ElementTree

NS = "{http://csrc.nist.gov/ns/oscal/metaschema/1.0}"

#: The vendored metaschema modules, in the order they are read.
MODULES = (
    "oscal_metadata_metaschema_RESOLVED.xml",
    "oscal_control-common_metaschema_RESOLVED.xml",
    "oscal_catalog_metaschema_RESOLVED.xml",
    "oscal_profile_metaschema_RESOLVED.xml",
    "oscal_implementation-common_metaschema_RESOLVED.xml",
    "oscal_component_metaschema_RESOLVED.xml",
    "oscal_ssp_metaschema_RESOLVED.xml",
    "oscal_assessment-common_metaschema_RESOLVED.xml",
    "oscal_assessment-plan_metaschema_RESOLVED.xml",
    "oscal_assessment-results_metaschema_RESOLVED.xml",
    "oscal_poam_metaschema_RESOLVED.xml",
    "oscal_mapping-common_metaschema_RESOLVED.xml",
    "oscal_mapping_metaschema_RESOLVED.xml",
)

#: Which OSCAL model each metaschema module governs. A module that governs one
#: model declares assemblies only that model has -- but assembly *names* repeat
#: across models (an SSP and a component definition each define an assembly
#: called ``implemented-requirement``, with different rules), so a constraint is
#: only ever applied to a document of the model its module governs. The shared
#: modules govern no single model and apply to every document.
MODULE_MODELS: dict[str, str] = {
    "oscal_catalog_metaschema_RESOLVED.xml": "catalog",
    "oscal_profile_metaschema_RESOLVED.xml": "profile",
    "oscal_ssp_metaschema_RESOLVED.xml": "system-security-plan",
    "oscal_component_metaschema_RESOLVED.xml": "component-definition",
    "oscal_assessment-plan_metaschema_RESOLVED.xml": "assessment-plan",
    "oscal_assessment-results_metaschema_RESOLVED.xml": "assessment-results",
    "oscal_poam_metaschema_RESOLVED.xml": "plan-of-action-and-milestones",
    "oscal_mapping_metaschema_RESOLVED.xml": "mapping-collection",
}

#: Constraint kinds this module knows how to evaluate at all.
EVALUATED_KINDS = ("is-unique", "index", "index-has-key", "has-cardinality")

#: Constraint kinds NIST declares that this module does not evaluate, with the
#: reason. Reported rather than ignored; see the README's "Limits".
UNEVALUATED_KINDS = {
    "expect": "the test is a Metapath expression, which this tool does not implement",
    "matches": "the value constraint is applied through Metapath datatype coercion",
    "allowed-values": "most allowed-value sets declare allow-other, so a value outside "
    "them is not necessarily a violation",
}

DEFINITION_TAGS = (f"{NS}define-assembly", f"{NS}define-field")
USE_TAGS = (f"{NS}assembly", f"{NS}field", f"{NS}define-assembly", f"{NS}define-field")

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Step:
    """One step of a bounded Metapath target expression."""

    names: tuple[str, ...]
    descendant: bool


@dataclass(frozen=True)
class KeyField:
    """One component of a constraint's key."""

    source: str
    pattern: str | None

    @property
    def is_flag(self) -> bool:
        return self.source.startswith("@")

    @property
    def flag(self) -> str:
        return self.source[1:]


@dataclass(frozen=True)
class Constraint:
    """One constraint as NIST published it, plus whether this tool runs it."""

    kind: str
    identifier: str
    level: str
    module: str
    context: str
    target: str
    index_name: str
    key_fields: tuple[KeyField, ...]
    min_occurs: int | None
    max_occurs: int | None
    steps: tuple[Step, ...] | None
    skipped: str

    @property
    def evaluated(self) -> bool:
        return not self.skipped

    @property
    def model(self) -> str | None:
        """The OSCAL model this constraint governs, or None for every model."""
        return MODULE_MODELS.get(self.module)

    def applies_to(self, model: str) -> bool:
        governed = self.model
        return governed is None or governed == model


@dataclass
class Metaschema:
    #: Definition name -> the name it goes by in a document.
    effective: dict[str, str]
    #: Effective name -> the JSON property names it can appear under.
    json_names: dict[str, frozenset[str]]
    constraints: tuple[Constraint, ...]

    def properties_for(self, name: str) -> frozenset[str]:
        return self.json_names.get(name, frozenset({name}))

    def evaluated(self, model: str | None = None) -> tuple[Constraint, ...]:
        return tuple(
            c for c in self.constraints if c.evaluated and (model is None or c.applies_to(model))
        )

    def skipped(self) -> tuple[Constraint, ...]:
        return tuple(c for c in self.constraints if not c.evaluated)


# -- parsing -----------------------------------------------------------------


def _text_of(element: ElementTree.Element, tag: str) -> str | None:
    child = element.find(f"{NS}{tag}")
    return child.text if child is not None and child.text else None


def _effective_name(element: ElementTree.Element) -> str:
    return _text_of(element, "use-name") or str(element.attrib.get("name", ""))


#: Markup that makes an XML document able to attack its parser. Both external
#: entity resolution and entity-expansion bombs need a DTD, so a document
#: declaring one is refused rather than parsed. The vendored files carry none;
#: a re-vendoring that introduced one would fail here and in the test suite.
FORBIDDEN_MARKUP = (b"<!DOCTYPE", b"<!ENTITY")


def read_module_bytes(name: str) -> bytes:
    """The bytes of one vendored metaschema module, checked before parsing.

    The only XML this tool ever parses is vendored, hash-pinned, and never
    supplied by a user: it is package data, read through ``importlib.resources``
    from a path the caller cannot influence, and ``tests/test_vendor_integrity``
    recomputes its SHA-256 on every run. The two attacks the standard library's
    parser is criticized for -- external entity resolution and entity-expansion
    bombs -- both require a DTD, so any document carrying one is refused before
    it reaches the parser rather than trusted to be harmless.

    The alternative, a third-party hardened parser, would put a runtime
    dependency in a package whose zero dependencies are what make its
    no-network and no-model claims mechanically checkable. See ADR-0003.
    """
    path = resources.files("oscal_validate").joinpath("vendor", "oscal", name)
    with path.open("rb") as handle:
        data: bytes = handle.read()
    for marker in FORBIDDEN_MARKUP:
        if marker in data:
            raise ValueError(
                f"vendored {name} contains {marker.decode()}, which this tool refuses to "
                "parse. Re-vendor from a NIST release and re-record the hash."
            )
    return data


def _read_module(name: str) -> ElementTree.Element:
    # nosemgrep: python.lang.security.use-defused-xml-parse
    # See read_module_bytes: the input is vendored, hash-pinned package data,
    # and any DTD is refused before this line is reached.
    return ElementTree.fromstring(read_module_bytes(name))  # noqa: S314


def parse_target(expression: str) -> tuple[Step, ...] | None:
    """Parse the bounded Metapath subset this tool evaluates, or return None.

    Supported: ``.``, ``name``, ``a/b``, ``a|b``, ``//name``, ``.//name``, and
    ``//(a|b|c)``. Everything else -- predicates, function calls, ``doc()``,
    axes -- returns None and the constraint is reported as not evaluated.
    """
    expression = expression.strip()
    if expression == ".":
        return ()
    descendant, expression = _strip_descendant(expression)
    if expression.startswith("("):
        return _parse_union(expression, descendant)
    if any(character in expression for character in "[]()@ :*"):
        return None
    if descendant:
        return None if "/" in expression else _step(expression, descendant=True)
    steps: list[Step] = []
    for segment in expression.split("/"):
        step = _step(segment, descendant=False)
        if step is None:
            return None
        steps.extend(step)
    return tuple(steps)


def _strip_descendant(expression: str) -> tuple[bool, str]:
    if expression.startswith(".//"):
        return True, expression[3:]
    if expression.startswith("//"):
        return True, expression[2:]
    return False, expression


def _parse_union(expression: str, descendant: bool) -> tuple[Step, ...] | None:
    if not descendant or not expression.endswith(")"):
        return None
    return _step(expression[1:-1], descendant=True)


def _step(segment: str, descendant: bool) -> tuple[Step, ...] | None:
    names = tuple(part.strip() for part in segment.split("|"))
    if not all(_NAME.match(name) for name in names):
        return None
    return (Step(names=names, descendant=descendant),)


def _integer(value: str | None) -> int | None:
    if value is None or value == "unbounded":
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - the vendored files are hash-checked
        return None


def _skip_reason(kind: str, steps: tuple[Step, ...] | None, target: str, context: str) -> str:
    if kind in UNEVALUATED_KINDS:
        return UNEVALUATED_KINDS[kind]
    if steps is None:
        return f"its target expression is outside the Metapath subset this tool parses: {target}"
    if not context:
        return "it is declared outside any assembly this tool can locate in a document"
    return ""


def _collect(root: ElementTree.Element, module: str) -> tuple[list[Constraint], dict[str, str]]:
    constraints: list[Constraint] = []
    effective: dict[str, str] = {}

    def walk(element: ElementTree.Element, context: str) -> None:
        for child in element:
            if child.tag in DEFINITION_TAGS:
                name = str(child.attrib.get("name", ""))
                if name:
                    effective[name] = _effective_name(child)
                walk(child, _effective_name(child))
            elif child.tag == f"{NS}constraint":
                constraints.extend(_constraints_in(child, module, context))
            else:
                walk(child, context)

    walk(root, "")
    return constraints, effective


def _constraints_in(element: ElementTree.Element, module: str, context: str) -> list[Constraint]:
    found: list[Constraint] = []
    for child in element:
        kind = child.tag.removeprefix(NS)
        if kind not in EVALUATED_KINDS and kind not in UNEVALUATED_KINDS:
            continue
        target = str(child.attrib.get("target", "."))
        steps = parse_target(target) if kind in EVALUATED_KINDS else None
        key_fields = tuple(
            KeyField(source=str(k.attrib.get("target", ".")), pattern=k.attrib.get("pattern"))
            for k in child
            if k.tag == f"{NS}key-field"
        )
        found.append(
            Constraint(
                kind=kind,
                identifier=str(child.attrib.get("id", "")),
                level=str(child.attrib.get("level", "ERROR")).upper(),
                module=module,
                context=context,
                target=target,
                index_name=str(child.attrib.get("name", "")),
                key_fields=key_fields,
                min_occurs=_integer(child.attrib.get("min-occurs")),
                max_occurs=_integer(child.attrib.get("max-occurs")),
                steps=steps,
                skipped=_skip_reason(kind, steps, target, context),
            )
        )
    return found


def _json_names(
    roots: list[tuple[str, ElementTree.Element]], effective: dict[str, str]
) -> dict[str, set[str]]:
    """Effective name -> every JSON property name it is grouped under."""
    names: dict[str, set[str]] = {}
    for _, root in roots:
        for parent in root.iter():
            for child in parent:
                if child.tag not in USE_TAGS:
                    continue
                ref = str(child.attrib.get("ref", ""))
                own = _effective_name(child) if not ref else effective.get(ref, ref)
                if not own:
                    continue
                group = child.find(f"{NS}group-as")
                json_name = str(group.attrib["name"]) if group is not None else own
                names.setdefault(own, set()).add(json_name)
    return names


@lru_cache(maxsize=1)
def load_metaschema() -> Metaschema:
    roots = [(name, _read_module(name)) for name in MODULES]
    constraints: list[Constraint] = []
    effective: dict[str, str] = {}
    for name, root in roots:
        module_constraints, module_effective = _collect(root, name)
        constraints.extend(module_constraints)
        effective.update(module_effective)
    names = _json_names(roots, effective)
    # A definition is also reachable under its own effective name.
    for own in effective.values():
        names.setdefault(own, set()).add(own)
    return Metaschema(
        effective=effective,
        json_names={key: frozenset(value) for key, value in names.items()},
        constraints=tuple(constraints),
    )


# -- evaluation --------------------------------------------------------------


@dataclass(frozen=True)
class Located:
    pointer: str
    value: Any


def select(
    node: Any, pointer: str, steps: tuple[Step, ...], metaschema: Metaschema
) -> list[Located]:
    """Apply a parsed target expression to a node."""
    current = [Located(pointer, node)]
    for step in steps:
        properties = frozenset().union(*(metaschema.properties_for(n) for n in step.names))
        current = (
            _descendants(current, properties) if step.descendant else _children(current, properties)
        )
    return current


def _expand(pointer: str, value: Any) -> list[Located]:
    if isinstance(value, list):
        return [Located(f"{pointer}/{index}", item) for index, item in enumerate(value)]
    return [Located(pointer, value)]


def _children(nodes: list[Located], properties: frozenset[str]) -> list[Located]:
    found: list[Located] = []
    for located in nodes:
        if not isinstance(located.value, dict):
            continue
        for key in properties:
            if key in located.value:
                found.extend(_expand(f"{located.pointer}/{key}", located.value[key]))
    return found


def _descendants(nodes: list[Located], properties: frozenset[str]) -> list[Located]:
    found: list[Located] = []
    for located in nodes:
        _walk_descendants(located.pointer, located.value, properties, found)
    return found


def _walk_descendants(
    pointer: str, value: Any, properties: frozenset[str], found: list[Located]
) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            child_pointer = f"{pointer}/{key}"
            if key in properties:
                found.extend(_expand(child_pointer, child))
            _walk_descendants(child_pointer, child, properties, found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_descendants(f"{pointer}/{index}", item, properties, found)


def key_values(node: Any, key_field: KeyField, metaschema: Metaschema) -> list[str] | None:
    """The value(s) a key-field selects from a node, or None when it selects nothing."""
    if key_field.source == ".":
        raw: list[Any] = [node] if not isinstance(node, dict | list) else []
    elif key_field.is_flag:
        if not isinstance(node, dict) or key_field.flag not in node:
            return None
        raw = [node[key_field.flag]]
    else:
        if not isinstance(node, dict):
            return None
        raw = []
        for name in metaschema.properties_for(key_field.source):
            value = node.get(name)
            if isinstance(value, list):
                raw.extend(value)
            elif value is not None:
                raw.append(value)
    if not raw:
        return None
    values = [str(item) for item in raw if not isinstance(item, dict | list)]
    if key_field.pattern is not None:
        matched = [re.match(key_field.pattern, value) for value in values]
        values = [m.group(1) if m.lastindex else m.group(0) for m in matched if m]
    return values or None


__all__ = [
    "EVALUATED_KINDS",
    "FORBIDDEN_MARKUP",
    "MODULES",
    "UNEVALUATED_KINDS",
    "Constraint",
    "KeyField",
    "Located",
    "Metaschema",
    "Step",
    "key_values",
    "load_metaschema",
    "parse_target",
    "read_module_bytes",
    "select",
]
