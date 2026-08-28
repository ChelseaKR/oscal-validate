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

#: Which OSCAL models each metaschema module governs. A module that governs one
#: model declares assemblies only that model has -- but assembly *names* repeat
#: across models (an SSP and a component definition each define an assembly
#: called ``implemented-requirement``, with different rules; a catalog's
#: ``part`` is control-common's, not assessment-common's), so a constraint is
#: only ever applied to a document of a model its module governs. The shared
#: modules that serve one family of models govern exactly that family;
#: ``metadata`` and ``control-common`` serve every model and are absent here.
MODULE_MODELS: dict[str, tuple[str, ...]] = {
    "oscal_catalog_metaschema_RESOLVED.xml": ("catalog",),
    "oscal_profile_metaschema_RESOLVED.xml": ("profile",),
    "oscal_ssp_metaschema_RESOLVED.xml": ("system-security-plan",),
    "oscal_component_metaschema_RESOLVED.xml": ("component-definition",),
    "oscal_implementation-common_metaschema_RESOLVED.xml": (
        "system-security-plan",
        "component-definition",
    ),
    "oscal_assessment-plan_metaschema_RESOLVED.xml": ("assessment-plan",),
    "oscal_assessment-results_metaschema_RESOLVED.xml": ("assessment-results",),
    "oscal_assessment-common_metaschema_RESOLVED.xml": (
        "assessment-plan",
        "assessment-results",
        "plan-of-action-and-milestones",
    ),
    "oscal_poam_metaschema_RESOLVED.xml": ("plan-of-action-and-milestones",),
    "oscal_mapping_metaschema_RESOLVED.xml": ("mapping-collection",),
    "oscal_mapping-common_metaschema_RESOLVED.xml": ("mapping-collection",),
}

#: Constraint kinds this module knows how to evaluate at all.
EVALUATED_KINDS = ("is-unique", "index", "index-has-key", "has-cardinality")

#: Constraint kinds NIST declares that this module does not evaluate, with the
#: sentence a report prints once per kind. The per-constraint reason is
#: computed by ``_skip_reason`` and published in ``docs/CONSTRAINT-COVERAGE.md``;
#: these are only the one-line summaries the report carries.
#:
#: The ``allowed-values`` sentence below is WRONG and is left in place under
#: protest. 60 of the 200 vendored sets declare ``allow-other``, not "most",
#: and the Metaschema specification makes the absent attribute mean the set is
#: closed, so the sentence has the default backwards. It cannot be corrected in
#: the same change that corrected the per-constraint reasons: this text reaches
#: the model through ``ai/walkthrough.py``'s prompt block, and the cassette at
#: ``tests/cassettes/walkthrough-nist-ssp.json`` is keyed on a hash of the exact
#: prompt, so changing one character here misses the recording and fails
#: ``tests/test_ai_walkthrough.py``. Re-recording is the procedure CONTRIBUTING
#: prescribes and it needs a live call on the owner's Bedrock account, which is
#: an owner action, not a code change. Until then the corrected reason is one
#: click away in the coverage document this sentence already points at.
UNEVALUATED_KINDS = {
    "expect": "the test is a Metapath expression, which this tool does not implement",
    "matches": "the value constraint is applied through Metapath datatype coercion",
    "allowed-values": "most allowed-value sets declare allow-other, so a value outside "
    "them is not necessarily a violation",
}

#: What the Metaschema specification says an absent ``allow-other`` means:
#:
#:     no: (default) Identifies the expected value set as closed. This is the
#:     implicit default value if no @allow-other is provided.
#:
#: Quoted rather than paraphrased, because it is the fact this repository had
#: backwards. The published skip reason for all 200 ``allowed-values``
#: constraints read "most allowed-value sets declare allow-other"; 60 of 200
#: declare it, and the other 140 are closed by this default.
#: https://pages.nist.gov/metaschema/specification/syntax/constraints/
ALLOW_OTHER_DEFAULT = "no"

DEFINITION_TAGS = (f"{NS}define-assembly", f"{NS}define-field")
USE_TAGS = (f"{NS}assembly", f"{NS}field", f"{NS}define-assembly", f"{NS}define-field")

_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*$")

#: The namespace a ``prop`` or ``part`` carries when it declares no ``ns`` flag.
#: NIST's metaschema declares this default on the ``ns`` flag itself.
OSCAL_NS = "http://csrc.nist.gov/ns/oscal"


@dataclass(frozen=True)
class Predicate:
    """One test inside a ``[...]`` predicate, from the enumerated bounded grammar.

    The four kinds are exactly the shapes the vendored 1.2.3 modules use
    (enumerated in ADR-0004, sized by evidence rather than by the Metapath
    specification): a flag equal to one of a set of strings, a flag starting
    with a prefix, ``has-oscal-namespace(...)``, and the existence of a child.
    """

    kind: str
    name: str
    values: tuple[str, ...]


@dataclass(frozen=True)
class Step:
    """One step of a bounded Metapath target expression.

    ``names`` empty means the context node itself (a ``.`` step): no traversal,
    only the predicates are applied.
    """

    names: tuple[str, ...]
    descendant: bool
    predicates: tuple[Predicate, ...] = ()


#: One parsed alternative of a target expression: a sequence of steps.
Path = tuple[Step, ...]


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
    paths: tuple[Path, ...] | None
    skipped: str
    #: ``allow-other`` as declared, or the published default where it is not.
    #: Only ever set on an ``allowed-values`` constraint.
    allow_other: str
    #: ``regex`` and ``datatype`` as declared on a ``matches`` constraint.
    regex: str
    datatype: str
    #: ``test`` as declared on an ``expect`` constraint.
    test: str

    @property
    def evaluated(self) -> bool:
        return not self.skipped

    @property
    def skip_group(self) -> str:
        """The one-line summary a report prints for this constraint's kind.

        Distinct from ``skipped``, which is this constraint's own reason and is
        what the coverage document prints. A report cannot print ``skipped``
        directly: each of the twelve ``expect`` constraints names its own test,
        so the kind would take twelve lines.
        """
        if not self.skipped:
            return ""
        return UNEVALUATED_KINDS.get(
            self.kind,
            "their target expressions are outside the Metapath subset this tool parses",
        )

    @property
    def models(self) -> tuple[str, ...] | None:
        """The OSCAL models this constraint governs, or None for every model."""
        return MODULE_MODELS.get(self.module)

    def applies_to(self, model: str) -> bool:
        governed = self.models
        return governed is None or model in governed


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


def parse_target(expression: str) -> tuple[Path, ...] | None:
    """Parse the bounded Metapath subset this tool evaluates, or return None.

    The result is a union of paths: most targets are a single path, and a
    top-level ``a|b/c`` union is every alternative, each parsed in full. A
    union any alternative of which cannot be parsed is refused whole, because
    evaluating a subset of a union changes what the constraint counts.

    Supported: ``.``, ``name``, ``a/b``, ``a|b``, ``//name``, ``.//name``,
    ``//(a|b|c)``, interior descendants (``a//b``), and the predicate forms
    enumerated from the vendored modules (ADR-0004): ``[@flag='v']``,
    ``[@flag=('v1','v2')]``, ``[starts-with(@flag,'v')]``,
    ``[has-oscal-namespace(...)]``, ``[child-name]``, and conjunctions of
    those with ``and``. Everything else -- other functions, ``doc()``, axes,
    wildcards -- returns None and the constraint is reported as not evaluated.
    """
    parts = _split_top(expression.strip(), "|")
    paths: list[Path] = []
    for part in parts:
        path = _parse_path(part.strip())
        if path is None:
            return None
        paths.append(path)
    return tuple(paths)


def _split_top(text: str, separator: str) -> list[str]:
    """Split on a separator character, ignoring any inside ``()`` or ``[]``."""
    parts: list[str] = []
    depth = 0
    start = 0
    for index, character in enumerate(text):
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif character == separator and depth == 0:
            parts.append(text[start:index])
            start = index + 1
    parts.append(text[start:])
    return parts


def _parse_path(text: str) -> Path | None:
    if text == ".":
        return ()
    descendant_next = False
    if text.startswith(".//"):
        descendant_next, text = True, text[3:]
    elif text.startswith("//"):
        descendant_next, text = True, text[2:]
    elif text.startswith("./") and not text.startswith(".//"):
        text = text[2:]
    if not text:
        return None
    steps: list[Step] = []
    segments = _split_top(text, "/")
    for index, raw_segment in enumerate(segments):
        segment = raw_segment.strip()
        if not segment:
            # An empty segment is the gap inside an interior ``//``.
            if descendant_next or index in (0, len(segments) - 1):
                return None
            descendant_next = True
            continue
        step = _parse_segment(segment, descendant_next)
        if step is None or (not step.names and index > 0):
            return None
        steps.append(step)
        descendant_next = False
    return tuple(steps)


def _parse_segment(segment: str, descendant: bool) -> Step | None:
    bracket = segment.find("[")
    name_part = segment if bracket == -1 else segment[:bracket]
    groups = [] if bracket == -1 else _bracket_groups(segment[bracket:])
    if groups is None:
        return None
    predicates: list[Predicate] = []
    for group in groups:
        parsed = _parse_conjunction(group)
        if parsed is None:
            return None
        predicates.extend(parsed)
    name_part = name_part.strip()
    if name_part == ".":
        return None if descendant else Step((), False, tuple(predicates))
    if name_part.startswith("(") and name_part.endswith(")"):
        if not descendant:
            return None
        names = tuple(part.strip() for part in name_part[1:-1].split("|"))
    else:
        names = (name_part,)
    if not all(_NAME.match(name) for name in names):
        return None
    return Step(names, descendant, tuple(predicates))


def _bracket_groups(text: str) -> list[str] | None:
    """The contents of consecutive balanced ``[...]`` groups, or None."""
    groups: list[str] = []
    while text:
        if not text.startswith("["):
            return None
        depth = 0
        for index, character in enumerate(text):
            if character == "[":
                depth += 1
            elif character == "]":
                depth -= 1
                if depth == 0:
                    groups.append(text[1:index])
                    text = text[index + 1 :]
                    break
        else:
            return None
    return groups


_FLAG_EQUALS = re.compile(r"@([A-Za-z][A-Za-z0-9._-]*)\s*=\s*(.+)$", re.DOTALL)
_STARTS_WITH = re.compile(
    r"starts-with\(\s*@([A-Za-z][A-Za-z0-9._-]*)\s*,\s*('[^']*'|\"[^\"]*\")\s*\)$"
)
_HAS_NAMESPACE = re.compile(r"has-oscal-namespace\((.+)\)$", re.DOTALL)


def _parse_conjunction(text: str) -> list[Predicate] | None:
    predicates: list[Predicate] = []
    for clause in _split_top_word(text, " and "):
        predicate = _parse_test(clause.strip())
        if predicate is None:
            return None
        predicates.append(predicate)
    return predicates


def _split_top_word(text: str, separator: str) -> list[str]:
    """Split on a separator word, ignoring any inside ``()`` or quotes."""
    parts: list[str] = []
    depth = 0
    quote = ""
    start = 0
    index = 0
    while index < len(text):
        character = text[index]
        if quote:
            if character == quote:
                quote = ""
        elif character in "'\"":
            quote = character
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        elif depth == 0 and text.startswith(separator, index):
            parts.append(text[start:index])
            index += len(separator)
            start = index
            continue
        index += 1
    parts.append(text[start:])
    return parts


def _parse_test(text: str) -> Predicate | None:
    match = _STARTS_WITH.fullmatch(text)
    if match:
        return Predicate("flag-starts-with", match.group(1), (match.group(2)[1:-1],))
    match = _HAS_NAMESPACE.fullmatch(text)
    if match:
        values = _string_or_set(match.group(1))
        return Predicate("oscal-namespace", "", values) if values else None
    match = _FLAG_EQUALS.fullmatch(text)
    if match:
        values = _string_or_set(match.group(2))
        return Predicate("flag-equals", match.group(1), values) if values else None
    if _NAME.match(text):
        return Predicate("child-exists", text, ())
    return None


def _string_or_set(text: str) -> tuple[str, ...] | None:
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1]
    values: list[str] = []
    for raw_piece in text.split(","):
        piece = raw_piece.strip()
        # A piece must be one whole quoted string. An embedded quote means the
        # text only looked like one -- ``'a' or @name='b'`` must not be read as
        # the value ``a' or @name='b``.
        if (
            len(piece) >= 2
            and piece[0] == piece[-1]
            and piece[0] in "'\""
            and piece[0] not in piece[1:-1]
        ):
            values.append(piece[1:-1])
        else:
            return None
    return tuple(values) if values else None


def _integer(value: str | None) -> int | None:
    if value is None or value == "unbounded":
        return None
    try:
        return int(value)
    except ValueError:  # pragma: no cover - the vendored files are hash-checked
        return None


@dataclass(frozen=True)
class _ConstraintAttributes:
    """The published attributes a skipped constraint's reason is computed from.

    Read straight off the element. ``allow_other`` carries the specification's
    default where the attribute is absent, so that the value in hand is always
    the effective one and no caller has to remember which way the default runs.
    """

    allow_other: str
    regex: str
    datatype: str
    test: str


def _attributes_of(element: ElementTree.Element, kind: str) -> _ConstraintAttributes:
    return _ConstraintAttributes(
        allow_other=(
            str(element.attrib.get("allow-other", ALLOW_OTHER_DEFAULT))
            if kind == "allowed-values"
            else ""
        ),
        regex=str(element.attrib.get("regex", "")) if kind == "matches" else "",
        datatype=str(element.attrib.get("datatype", "")) if kind == "matches" else "",
        test=str(element.attrib.get("test", "")) if kind == "expect" else "",
    )


def _unparsed_target_reason(target: str) -> str:
    if "doc(" in target:
        return (
            "its target dereferences a second document through doc(), which this tool "
            f"does not implement: {target}"
        )
    return f"its target expression is outside the Metapath subset this tool parses: {target}"


def _value_constraint_reason(
    kind: str, attributes: _ConstraintAttributes, target: str, context: str
) -> str:
    """Why one ``allowed-values``, ``matches`` or ``expect`` constraint is skipped.

    Computed from what the constraint declares, so that a reader is told the
    specific thing that is missing rather than a sentence about its kind. The
    three kinds are blocked for three different reasons and, within
    ``allowed-values``, for two.
    """
    if kind == "allowed-values":
        if attributes.allow_other == "yes":
            return (
                'it declares allow-other="yes", which opens its value set only if every '
                "other allowed-values constraint sharing its target does too, and this "
                "tool does not resolve that applicable set"
            )
        return (
            "its value set is closed, since allow-other defaults to "
            f'"{ALLOW_OTHER_DEFAULT}" where it is not declared, and this tool does not '
            "resolve the applicable set of constraints sharing its target, which is what "
            "decides the permitted values"
        )
    if kind == "matches":
        against = " and ".join(
            part
            for part in (
                f"the regex {attributes.regex}" if attributes.regex else "",
                f"the datatype {attributes.datatype}" if attributes.datatype else "",
            )
            if part
        )
        return (
            f"it constrains a value against {against}, and this tool does not select the "
            f"value its target names: {target}"
        )
    return (
        f"its test is a Metapath expression this tool does not implement: {attributes.test}"
    ) + (f" (on {context})" if context else "")


def _skip_reason(
    kind: str,
    paths: tuple[Path, ...] | None,
    target: str,
    context: str,
    attributes: _ConstraintAttributes,
) -> str:
    if kind in UNEVALUATED_KINDS:
        return _value_constraint_reason(kind, attributes, target, context)
    if paths is None:
        return _unparsed_target_reason(target)
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
        paths = parse_target(target) if kind in EVALUATED_KINDS else None
        attributes = _attributes_of(child, kind)
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
                paths=paths,
                skipped=_skip_reason(kind, paths, target, context, attributes),
                allow_other=attributes.allow_other,
                regex=attributes.regex,
                datatype=attributes.datatype,
                test=attributes.test,
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
                # A use-site ``use-name`` renames the node at that use: the
                # SSP uses ``system-component`` under the name ``component``,
                # and that is the name NIST's constraint targets select by.
                use_name = _text_of(child, "use-name")
                if use_name:
                    own = use_name
                elif ref:
                    own = effective.get(ref, ref)
                else:
                    own = _effective_name(child)
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


def select(node: Any, pointer: str, steps: Path, metaschema: Metaschema) -> list[Located]:
    """Apply one parsed path to a node."""
    current = [Located(pointer, node)]
    for step in steps:
        if step.names:
            properties = frozenset().union(*(metaschema.properties_for(n) for n in step.names))
            current = (
                _descendants(current, properties)
                if step.descendant
                else _children(current, properties)
            )
        if step.predicates:
            current = [
                located
                for located in current
                if _admits(located.value, step.predicates, metaschema)
            ]
    return current


def select_paths(
    node: Any, pointer: str, paths: tuple[Path, ...], metaschema: Metaschema
) -> list[Located]:
    """Apply a union of paths, deduplicated by location.

    Deduplication is what makes a union target safe to count: the alternatives
    of ``responsible-role|statement/responsible-role|.//by-component//responsible-role``
    overlap, and a node reached twice must be one entry in a uniqueness index
    and one occurrence in a cardinality count, not two.
    """
    found: list[Located] = []
    seen: set[str] = set()
    for path in paths:
        for located in select(node, pointer, path, metaschema):
            if located.pointer in seen:
                continue
            seen.add(located.pointer)
            found.append(located)
    return found


def _admits(value: Any, predicates: tuple[Predicate, ...], metaschema: Metaschema) -> bool:
    """Whether one node satisfies every predicate of a step."""
    return all(_admits_one(value, predicate, metaschema) for predicate in predicates)


def _admits_one(value: Any, predicate: Predicate, metaschema: Metaschema) -> bool:
    if predicate.kind == "flag-equals":
        if not isinstance(value, dict) or predicate.name not in value:
            return False
        flag = value[predicate.name]
        return not isinstance(flag, dict | list) and str(flag) in predicate.values
    if predicate.kind == "flag-starts-with":
        if not isinstance(value, dict):
            return False
        flag = value.get(predicate.name)
        return isinstance(flag, str) and flag.startswith(predicate.values[0])
    if predicate.kind == "oscal-namespace":
        namespace = value.get("ns", OSCAL_NS) if isinstance(value, dict) else OSCAL_NS
        return isinstance(namespace, str) and namespace in predicate.values
    # child-exists: the named child selects at least one node under any of its
    # JSON property names. An empty array is a property with zero nodes.
    if not isinstance(value, dict):
        return False
    for name in metaschema.properties_for(predicate.name):
        child = value.get(name)
        if child is None or (isinstance(child, list) and not child):
            continue
        return True
    return False


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
    "ALLOW_OTHER_DEFAULT",
    "EVALUATED_KINDS",
    "FORBIDDEN_MARKUP",
    "MODULES",
    "OSCAL_NS",
    "UNEVALUATED_KINDS",
    "Constraint",
    "KeyField",
    "Located",
    "Metaschema",
    "Path",
    "Predicate",
    "Step",
    "key_values",
    "load_metaschema",
    "parse_target",
    "read_module_bytes",
    "select",
    "select_paths",
]
