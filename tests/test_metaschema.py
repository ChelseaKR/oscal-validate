"""The constraint layer, parsed out of the vendored metaschema files.

These tests pin two things: that the Metapath subset is exactly the subset it
claims to be, and that the coverage numbers the tool reports are the numbers
the vendored files actually contain. A coverage claim that drifts from its
source is worse than no claim.
"""

from __future__ import annotations

from collections import Counter
from xml.etree import ElementTree

import pytest

from oscal_validate.metaschema import (
    ALLOW_OTHER_DEFAULT,
    DEFINITION_TAGS,
    EVALUATED_KINDS,
    MODULES,
    NS,
    OSCAL_NS,
    UNEVALUATED_KINDS,
    VALUE_KINDS,
    KeyField,
    Path,
    Predicate,
    Step,
    key_values,
    load_metaschema,
    parse_target,
    parse_value_target,
    read_module_bytes,
    select,
    select_paths,
    select_values,
)

#: The published constraint inventory of OSCAL 1.2.3, and what this tool runs.
#: Both halves are asserted so that a re-vendoring shows a reviewable diff.
PUBLISHED = {
    "allowed-values": 200,
    "expect": 12,
    "has-cardinality": 11,
    "index": 20,
    "index-has-key": 24,
    "is-unique": 48,
    "matches": 25,
}
EVALUATED = {"has-cardinality": 11, "index": 19, "index-has-key": 24, "is-unique": 48}


def test_the_published_constraint_inventory_is_what_we_say_it_is() -> None:
    metaschema = load_metaschema()
    assert Counter(c.kind for c in metaschema.constraints) == Counter(PUBLISHED)


def test_the_evaluated_subset_is_what_we_say_it_is() -> None:
    metaschema = load_metaschema()
    assert Counter(c.kind for c in metaschema.evaluated()) == Counter(EVALUATED)
    assert len(metaschema.evaluated()) == 102
    assert len(metaschema.constraints) == 340


def test_every_skipped_constraint_says_why() -> None:
    for constraint in load_metaschema().skipped():
        assert constraint.skipped, constraint.identifier


def test_no_constraint_is_evaluated_without_a_parsed_target() -> None:
    for constraint in load_metaschema().evaluated():
        assert constraint.kind in EVALUATED_KINDS
        assert constraint.paths is not None
        assert constraint.context


def test_the_unevaluated_kinds_are_declared_with_reasons() -> None:
    for kind, reason in UNEVALUATED_KINDS.items():
        assert kind in PUBLISHED
        assert reason


@pytest.mark.parametrize(
    ("expression", "expected"),
    [
        (".", ((),)),
        ("role", ((Step(("role",), False),),)),
        ("//control", ((Step(("control",), True),),)),
        (".//prop", ((Step(("prop",), True),),)),
        ("//(control|group|part)", ((Step(("control", "group", "part"), True),),)),
        ("rlink|base64", ((Step(("rlink",), False),), (Step(("base64",), False),))),
        ("component/link", ((Step(("component",), False), Step(("link",), False)),)),
        # Interior descendants: the shape oscal-by-component-export-provided-uuid-index uses.
        (
            "implemented-requirement//by-component/export",
            (
                (
                    Step(("implemented-requirement",), False),
                    Step(("by-component",), True),
                    Step(("export",), False),
                ),
            ),
        ),
        # The predicate forms enumerated from the vendored modules (ADR-0004).
        (
            "component[@type='service']",
            ((Step(("component",), False, (Predicate("flag-equals", "type", ("service",)),)),),),
        ),
        (
            "link[@rel='diagram' and starts-with(@href,'#')]",
            (
                (
                    Step(
                        ("link",),
                        False,
                        (
                            Predicate("flag-equals", "rel", ("diagram",)),
                            Predicate("flag-starts-with", "href", ("#",)),
                        ),
                    ),
                ),
            ),
        ),
        (
            ".[@rel=('reference') and starts-with(@href,'#')]",
            (
                (
                    Step(
                        (),
                        False,
                        (
                            Predicate("flag-equals", "rel", ("reference",)),
                            Predicate("flag-starts-with", "href", ("#",)),
                        ),
                    ),
                ),
            ),
        ),
        (
            "prop[has-oscal-namespace(('http://csrc.nist.gov/ns/oscal',"
            "'http://csrc.nist.gov/ns/rmf'))]",
            (
                (
                    Step(
                        ("prop",),
                        False,
                        (
                            Predicate(
                                "oscal-namespace",
                                "",
                                (
                                    "http://csrc.nist.gov/ns/oscal",
                                    "http://csrc.nist.gov/ns/rmf",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
        (
            "responsible-role[party-uuid]|statement/responsible-role[party-uuid]",
            (
                (
                    Step(
                        ("responsible-role",),
                        False,
                        (Predicate("child-exists", "party-uuid", ()),),
                    ),
                ),
                (
                    Step(("statement",), False),
                    Step(
                        ("responsible-role",),
                        False,
                        (Predicate("child-exists", "party-uuid", ()),),
                    ),
                ),
            ),
        ),
    ],
)
def test_the_supported_metapath_subset_parses(
    expression: str, expected: tuple[tuple[Step, ...], ...]
) -> None:
    assert parse_target(expression) == expected


@pytest.mark.parametrize(
    "expression",
    [
        "doc(system-implementation/leveraged-authorization/link/@href)/system-security-plan",
        # A union any alternative of which fails is refused whole: evaluating a
        # subset of a union would change what the constraint counts.
        "by-component|doc(link/@href)/system-security-plan//by-component",
        "//(control|group",
        "child::control",
        "*",
        "part[1]",
        "part[position()=1]",
        "link[@rel!='reference']",
        "prop[not(@name)]",
        "prop[@name='a' or @name='b']",
        "link[starts-with(@href,concat('#','x'))]",
        "a/",
        "/a",
        "a///b",
        "a[@x='v'",
    ],
)
def test_expressions_outside_the_subset_are_refused_rather_than_guessed(expression: str) -> None:
    assert parse_target(expression) is None


def test_select_walks_json_by_the_names_the_metaschema_groups_them_under() -> None:
    metaschema = load_metaschema()
    document = {
        "catalog": {
            "groups": [{"id": "g", "controls": [{"id": "c1"}, {"id": "c2"}]}],
            "controls": [{"id": "c3"}],
        }
    }
    found = select(document, "", (Step(("control",), True),), metaschema)
    assert sorted(located.value["id"] for located in found) == ["c1", "c2", "c3"]
    assert "/catalog/groups/0/controls/0" in {located.pointer for located in found}


def test_key_fields_read_flags_children_and_patterns() -> None:
    metaschema = load_metaschema()
    node = {"role-id": "admin", "party-uuids": ["a", "b"], "href": "#abc123"}
    assert key_values(node, KeyField("@role-id", None), metaschema) == ["admin"]
    assert key_values(node, KeyField("party-uuid", None), metaschema) == ["a", "b"]
    assert key_values(node, KeyField("@href", "#(.*)"), metaschema) == ["abc123"]
    assert key_values(node, KeyField("@missing", None), metaschema) is None


def test_a_pattern_that_does_not_match_selects_nothing() -> None:
    metaschema = load_metaschema()
    assert (
        key_values({"href": "https://example.org"}, KeyField("@href", "#(.*)"), metaschema) is None
    )


def test_predicates_filter_selection_by_what_the_node_actually_carries() -> None:
    metaschema = load_metaschema()
    paths = parse_target("component[@type='service']")
    assert paths is not None
    document = {
        "components": [
            {"uuid": "a", "type": "service"},
            {"uuid": "b", "type": "software"},
            {"uuid": "c"},
        ]
    }
    found = select_paths(document, "", paths, metaschema)
    assert [located.value["uuid"] for located in found] == ["a"]


def test_has_oscal_namespace_defaults_an_absent_ns_to_the_oscal_namespace() -> None:
    metaschema = load_metaschema()
    paths = parse_target(
        "prop[has-oscal-namespace(('http://csrc.nist.gov/ns/oscal','http://csrc.nist.gov/ns/rmf'))]"
    )
    assert paths is not None
    document = {
        "props": [
            {"name": "defaulted"},
            {"name": "oscal", "ns": OSCAL_NS},
            {"name": "rmf", "ns": "http://csrc.nist.gov/ns/rmf"},
            {"name": "other", "ns": "http://example.test/ns"},
        ]
    }
    found = select_paths(document, "", paths, metaschema)
    assert [located.value["name"] for located in found] == ["defaulted", "oscal", "rmf"]


def test_child_existence_resolves_grouped_json_names_and_ignores_empty_arrays() -> None:
    metaschema = load_metaschema()
    paths = parse_target("responsible-role[party-uuid]")
    assert paths is not None
    document = {
        "responsible-roles": [
            {"role-id": "with", "party-uuids": ["x"]},
            {"role-id": "empty", "party-uuids": []},
            {"role-id": "without"},
        ]
    }
    found = select_paths(document, "", paths, metaschema)
    assert [located.value["role-id"] for located in found] == ["with"]


def test_a_union_of_overlapping_paths_selects_each_node_once() -> None:
    metaschema = load_metaschema()
    paths = parse_target("responsible-role|.//responsible-role")
    assert paths is not None
    document = {"responsible-roles": [{"role-id": "r1"}], "statements": []}
    found = select_paths(document, "", paths, metaschema)
    assert len(found) == 1


# -- the reason a constraint is skipped ---------------------------------------


def _declared_value_constraints() -> list[tuple[str, dict[str, str]]]:
    """Every allowed-values, matches and expect element, re-read from the files.

    Deliberately a second, independent read: it walks the vendored XML with
    ElementTree directly rather than going through ``load_metaschema``, so a
    reason that is a constant in the parser cannot satisfy an assertion made
    against what the file declares.
    """
    found: list[tuple[str, dict[str, str]]] = []
    for name in MODULES:
        # nosemgrep: python.lang.security.use-defused-xml-parse
        # Same input and same guard as metaschema.py: hash-pinned package data
        # read through read_module_bytes, which refuses any file with a DTD.
        root = ElementTree.fromstring(read_module_bytes(name))  # noqa: S314
        for element in root.iter():
            kind = element.tag.removeprefix(NS)
            if kind in ("allowed-values", "matches", "expect"):
                found.append((kind, dict(element.attrib)))
    return found


def test_the_vendored_files_declare_allow_other_on_a_minority_of_sets() -> None:
    """The count the published skip reason got backwards.

    It read "most allowed-value sets declare allow-other". They do not, and the
    Metaschema specification makes the absent attribute mean the opposite of
    what that sentence implies: "no: (default) Identifies the expected value
    set as closed."
    """
    sets = [
        attributes for kind, attributes in _declared_value_constraints() if kind == "allowed-values"
    ]
    declared = [a for a in sets if "allow-other" in a]
    assert len(sets) == 200
    assert len(declared) == 60
    assert len(sets) - len(declared) == 140
    assert ALLOW_OTHER_DEFAULT == "no"


def test_every_skipped_reason_names_what_that_constraint_declares() -> None:
    """The reason is computed per constraint, not looked up by kind.

    Each assertion below is against the attribute the vendored file carries on
    that one element, so a per-kind constant cannot satisfy it.
    """
    skipped = {c.identifier: c for c in load_metaschema().skipped() if c.identifier}
    checked = 0
    for kind, attributes in _declared_value_constraints():
        constraint = skipped.get(attributes.get("id", ""))
        if constraint is None:
            continue
        checked += 1
        reason = constraint.skipped
        if constraint.value_target is None and kind in VALUE_KINDS:
            # Blocked before its own declarations matter: the target cannot be
            # read, so the reason names that and nothing further.
            assert "outside the subset this tool parses" in reason, constraint.identifier
            continue
        if constraint.declared_on_flag:
            assert "is declared on the flag" in reason, constraint.identifier
            continue
        if kind == "allowed-values":
            if attributes.get("allow-other") == "yes":
                assert 'allow-other="yes"' in reason, constraint.identifier
            else:
                assert f'defaults to "{ALLOW_OTHER_DEFAULT}"' in reason, constraint.identifier
        elif kind == "matches":
            for attribute in ("regex", "datatype"):
                if attribute in attributes:
                    assert attributes[attribute] in reason, constraint.identifier
        else:
            assert attributes["test"] in reason, constraint.identifier
    assert checked >= 200


def test_a_kind_blocked_several_ways_publishes_several_reasons() -> None:
    """The failure this work exists to prevent, asserted directly.

    The 200 allowed-values constraints are not blocked for one reason. Some
    have targets this tool cannot read, some are declared on a flag, and of
    the rest 140 are closed sets and 60 declare allow-other. One sentence
    covering all of them is how the wrong one got published.
def test_a_kind_blocked_for_two_reasons_publishes_two_reasons() -> None:
    """The failure this phase exists to prevent, asserted directly.

    200 allowed-values constraints are not blocked for one reason: 140 are
    closed sets and 60 declare allow-other. One sentence covering all of them
    is how the wrong one got published.
    """
    by_kind: dict[str, set[str]] = {}
    for constraint in load_metaschema().skipped():
        by_kind.setdefault(constraint.kind, set()).add(constraint.skipped)
    reasons = by_kind["allowed-values"]
    assert len(reasons) > 2
    assert sum(1 for r in reasons if 'allow-other="yes"' in r) == 1
    assert sum(1 for r in reasons if f'defaults to "{ALLOW_OTHER_DEFAULT}"' in r) == 1
    assert len(by_kind["allowed-values"]) == 2
    # Every expect constraint names its own test, so no two share a reason.
    assert len(by_kind["expect"]) == 12


def test_the_kind_summary_and_the_constraint_reason_are_separate_things() -> None:
    """A report prints one summary per kind; the coverage document prints 238 reasons.

    Keeping them separate is what let the per-constraint reasons be corrected
    without touching a byte of report output. The kind summary is corrected
    separately, and is blocked: it reaches the model through the walkthrough
    prompt, and the cassette is keyed on that prompt.
    """
    groups: dict[str, set[str]] = {}
    for constraint in load_metaschema().skipped():
        groups.setdefault(constraint.kind, set()).add(constraint.skip_group)
    assert all(len(value) == 1 for value in groups.values())
    for constraint in load_metaschema().skipped():
        assert constraint.skip_group != constraint.skipped
    for constraint in load_metaschema().evaluated():
        assert constraint.skip_group == ""


# -- value targets ------------------------------------------------------------


@pytest.mark.parametrize(
    ("expression", "flag", "steps"),
    [
        # A bare flag step: the specification's "flag use case", where the
        # target is the flag's own value and no path is walked.
        ("@resource-fragment", "resource-fragment", ((),)),
        # A flag on the nodes a path selects.
        ("link/@rel", "rel", ((Step(("link",), False),),)),
        # The context node's own value, with and without a predicate.
        (".", "", ((),)),
        (
            ".[@algorithm=('SHA-256')]",
            "",
            ((Step((), False, (Predicate("flag-equals", "algorithm", ("SHA-256",)),)),),),
        ),
    ],
)
def test_a_value_target_parses_the_shapes_the_vendored_files_use(
    expression: str, flag: str, steps: tuple[Path, ...]
) -> None:
    parsed = parse_value_target(expression)
    assert parsed is not None
    assert parsed.flag == flag
    assert parsed.paths == steps


@pytest.mark.parametrize(
    "expression",
    [
        # A union whose alternatives carry their own flag steps. Reading only
        # the last alternative would check a fraction of the values NIST wrote.
        "responsible-role/@role-id|control-implementation/responsible-role/@role-id",
        # A parenthesised context step carrying predicates: not in the node
        # grammar, so the value target is refused whole rather than in part.
        "(.)[@type='software']/prop/@name",
        # A flag with a predicate on the flag itself.
        "link[@rel='diagram']/@href[starts-with(.,'#')]",
        # Not a flag name.
        "prop/@",
        "prop/@1bad",
    ],
)
def test_a_value_target_outside_the_enumerated_shapes_is_refused(expression: str) -> None:
    assert parse_value_target(expression) is None


def test_the_value_targets_that_parse_are_counted_and_pinned() -> None:
    """Parsing a target is not evaluating a constraint, so no count of evaluated moves.

    These numbers move when the grammar widens, which is the point of pinning
    them: a widening that claims more reach than it has fails here.
    """
    constraints = load_metaschema().constraints
    parsed = {
        kind: sum(1 for c in constraints if c.kind == kind and c.value_target is not None)
        for kind in VALUE_KINDS
    }
    assert parsed == {"allowed-values": 155, "matches": 18}
    assert len(load_metaschema().evaluated()) == 102


def test_a_constraint_declared_on_a_flag_is_recorded_against_that_flag() -> None:
    """The context of a constraint inside a define-flag is not the enclosing assembly.

    Before this was read, all 43 of them carried the reason written for a
    constraint on an assembly, which pointed a reader at the wrong node. The
    count is re-derived from the vendored XML rather than trusted.
    """
    declared = 0
    for name in MODULES:
        # nosemgrep: python.lang.security.use-defused-xml-parse
        root = ElementTree.fromstring(read_module_bytes(name))  # noqa: S314
        parents = {child: parent for parent in root.iter() for child in parent}
        for element in root.iter():
            if element.tag.removeprefix(NS) not in ("allowed-values", "matches", "expect"):
                continue
            walker = parents.get(element)
            while walker is not None:
                tag = walker.tag
                if tag == f"{NS}define-flag":
                    declared += 1
                    break
                if tag in DEFINITION_TAGS:
                    break
                walker = parents.get(walker)
    assert declared == 43

    on_flag = [c for c in load_metaschema().constraints if c.declared_on_flag]
    assert len(on_flag) == declared
    for constraint in on_flag:
        assert "is declared on the flag" in constraint.skipped
        assert constraint.declared_on_flag in constraint.skipped


def test_json_value_keys_are_read_from_the_vendored_files() -> None:
    """A field that declares flags writes its own value under a declared key."""
    value_keys = load_metaschema().value_keys
    assert value_keys["hash"] == "value"
    assert value_keys["telephone-number"] == "number"
    assert value_keys["document-id"] == "identifier"
    # A field with no flags is the scalar itself and declares no key.
    assert load_metaschema().value_key_for("title") == ""


def test_select_values_reads_a_flag_a_scalar_and_a_declared_value_key() -> None:
    metaschema = load_metaschema()
    document = {
        "hash": {"algorithm": "SHA-256", "value": "abc"},
        "links": [{"rel": "reference", "href": "#x"}, {"href": "#y"}],
        "title": "a title",
    }
    flag_target = parse_value_target("links/@rel")
    assert flag_target is not None
    found = select_values(document, "", flag_target, metaschema)
    # The link with no rel flag is not selected; a missing flag is not a value.
    assert [(f.pointer, f.value) for f in found] == [("/links/0/rel", "reference")]

    scalar_target = parse_value_target("title")
    assert scalar_target is not None
    assert [f.value for f in select_values(document, "", scalar_target, metaschema)] == ["a title"]

    own_target = parse_value_target("hash")
    assert own_target is not None
    # Without the declared key the object carries no value this tool can read.
    assert select_values(document, "", own_target, metaschema) == []
    with_key = select_values(document, "", own_target, metaschema, value_key="value")
    assert [(f.pointer, f.value) for f in with_key] == [("/hash/value", "abc")]
