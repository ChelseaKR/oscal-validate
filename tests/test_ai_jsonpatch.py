"""Pointers resolve, the three operations apply to a copy, everything else is refused."""

from __future__ import annotations

import pytest

from oscal_validate.ai.jsonpatch import (
    Operation,
    PatchError,
    apply,
    escape,
    parent_pointer,
    resolve,
    split,
)


def test_pointer_tokens_unescape_and_resolve() -> None:
    doc = {"a": {"b/c": [10, {"~d": "x"}]}}
    assert split("/a/b~1c/1/~0d") == ["a", "b/c", "1", "~d"]
    assert resolve(doc, "/a/b~1c/1/~0d") == "x"
    assert resolve(doc, "") is doc
    assert escape("b/c~") == "b~1c~0"
    assert parent_pointer("/a/b~1c/1") == "/a/b~1c"
    assert parent_pointer("/a") == ""


@pytest.mark.parametrize(
    "pointer",
    ["a", "/missing", "/a/b~1c/9", "/a/b~1c/x", "/a/b~1c/0/deeper"],
)
def test_a_bad_pointer_names_the_failing_step(pointer: str) -> None:
    doc = {"a": {"b/c": [10, {"~d": "x"}]}}
    with pytest.raises(PatchError):
        resolve(doc, pointer)


def test_operations_apply_in_order_to_a_copy_and_never_to_the_input() -> None:
    doc = {"m": {"title": "t"}, "items": [1, 2]}
    ops = [
        Operation("add", "/m/last-modified", "2026-08-14T00:00:00Z"),
        Operation("replace", "/m/title", "new"),
        Operation("remove", "/items/0"),
        Operation("add", "/items/-", 3),
        Operation("add", "/items/0", 0),
    ]
    out = apply(doc, ops)
    assert out == {
        "m": {"title": "new", "last-modified": "2026-08-14T00:00:00Z"},
        "items": [0, 2, 3],
    }
    assert doc == {"m": {"title": "t"}, "items": [1, 2]}


def test_replace_and_remove_need_an_existing_target() -> None:
    doc: dict[str, object] = {"m": {}, "items": []}
    with pytest.raises(PatchError, match="no property"):
        apply(doc, [Operation("replace", "/m/x", 1)])
    with pytest.raises(PatchError, match="past the end"):
        apply(doc, [Operation("remove", "/items/0")])
    with pytest.raises(PatchError, match="whole document"):
        apply(doc, [Operation("replace", "", {})])
    with pytest.raises(PatchError, match="parent is a"):
        apply({"s": "text"}, [Operation("add", "/s/x", 1)])


def test_only_add_remove_replace_are_accepted() -> None:
    assert Operation.from_dict({"op": "remove", "path": "/a"}).to_dict() == {
        "op": "remove",
        "path": "/a",
    }
    with pytest.raises(PatchError, match="not one of"):
        Operation.from_dict({"op": "move", "from": "/a", "path": "/b"})
    with pytest.raises(PatchError, match="needs a value"):
        Operation.from_dict({"op": "add", "path": "/a"})
    with pytest.raises(PatchError, match="string path"):
        Operation.from_dict({"op": "add", "path": 3, "value": 1})
