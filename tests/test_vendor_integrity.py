"""The vendored files must be exactly the ones SOURCES.md cites.

If a vendored file changes without its recorded hash changing, every citation
in every finding becomes suspect. This gate makes that impossible to miss.
"""

from __future__ import annotations

import hashlib
import io
import re
from importlib import resources

import pytest

from oscal_validate.metaschema import MODULES
from oscal_validate.schema import VENDORED_SCHEMA, schema_release

EXPECTED = {
    "oscal/complete_schema.json": (
        "384324105c7a817af0f65b120a963146caa0e0d55d969cf0daf60e063b87a206"
    ),
    "oscal/oscal_assessment-common_metaschema_RESOLVED.xml": (
        "260b8163dabea22199ea8c342298adabe5b8effa7ad955657f0066c62fbe9660"
    ),
    "oscal/oscal_assessment-plan_metaschema_RESOLVED.xml": (
        "5505756506e60028d5e755fd926980763dc7a15c49e1ce09c1e4ee7f82200651"
    ),
    "oscal/oscal_assessment-results_metaschema_RESOLVED.xml": (
        "51a0960f2344a704af93c41361cfe340b8983f25abc291a461af4f727db767ac"
    ),
    "oscal/oscal_catalog_metaschema_RESOLVED.xml": (
        "775f8326e3dac336be17c4f7eefa89661053230fb1e8538364186c927ee062b1"
    ),
    "oscal/oscal_component_metaschema_RESOLVED.xml": (
        "86a91b71538bb59161b41e6394282d3983c2ad049923a3aea70d2f034c86138c"
    ),
    "oscal/oscal_control-common_metaschema_RESOLVED.xml": (
        "211517a6f94c9cba6644f2e0956986af0a5d36cf893259b1635b73dd6bd06542"
    ),
    "oscal/oscal_implementation-common_metaschema_RESOLVED.xml": (
        "3ea7b81bd48111fade0c1c7159bba192123f31c7f7d85dfcbee7c84cfb3b3870"
    ),
    "oscal/oscal_mapping_metaschema_RESOLVED.xml": (
        "07e4df2c0bf05750bd9b359debd5fd5d5d7f1635c867bcd9bd1e55cb5afc0754"
    ),
    "oscal/oscal_mapping-common_metaschema_RESOLVED.xml": (
        "ab036cd28543112c0bd5ad6def844b37e0a65d00b0a6a19b1cf1ede33431fea0"
    ),
    "oscal/oscal_metadata_metaschema_RESOLVED.xml": (
        "3d41842502a36c95554c281c79d0c2d533e4e956f0409b36cdede7001cec1b22"
    ),
    "oscal/oscal_poam_metaschema_RESOLVED.xml": (
        "bc8a90496eb9d762c6cb5dc3f18e252236ffbbc16e544f761ae4a12039d05e13"
    ),
    "oscal/oscal_profile_metaschema_RESOLVED.xml": (
        "ecef5ed68d793c59d2b659633e1c30633ee077e7d76f9894551ef06cadb083d9"
    ),
    "oscal/oscal_ssp_metaschema_RESOLVED.xml": (
        "2ffc8504bffe8f5dd7f2f689f48f308bf062950abeb438ddba9a89ca03a70ffe"
    ),
}


def _vendor_bytes(relpath: str) -> bytes:
    path = resources.files("oscal_validate").joinpath("vendor").joinpath(relpath)
    with path.open("rb") as handle:
        data: bytes = handle.read()
    return data


def test_vendored_files_match_recorded_hashes() -> None:
    for relpath, expected in EXPECTED.items():
        actual = hashlib.sha256(_vendor_bytes(relpath)).hexdigest()
        assert actual == expected, f"{relpath} does not match the hash recorded in SOURCES.md"


def test_sources_md_records_the_same_hashes() -> None:
    text = _vendor_bytes("SOURCES.md").decode("utf-8")
    for relpath, expected in EXPECTED.items():
        row = re.search(rf"`{re.escape(relpath)}`.*`([0-9a-f]{{64}})`", text)
        assert row is not None, f"SOURCES.md has no hash row for {relpath}"
        assert row.group(1) == expected


def test_every_vendored_file_is_hashed() -> None:
    # A file that arrives in vendor/ without a hash row would be an unchecked
    # rule source, which is the one thing this repository must not have.
    listed = {VENDORED_SCHEMA, *(f"oscal/{name}" for name in MODULES)}
    assert listed == set(EXPECTED)


def test_the_release_the_schema_declares_is_the_one_we_cite() -> None:
    from oscal_validate.rules import OSCAL_RELEASE

    assert schema_release() == OSCAL_RELEASE


def test_no_vendored_metaschema_carries_a_dtd() -> None:
    # The only XML this tool parses is vendored and hash-pinned. Both attacks
    # the standard library parser is criticized for need a DTD, so a document
    # carrying one is refused rather than trusted.
    from oscal_validate.metaschema import FORBIDDEN_MARKUP, read_module_bytes

    for name in MODULES:
        data = read_module_bytes(name)
        assert not any(marker in data for marker in FORBIDDEN_MARKUP), name


def test_a_vendored_file_carrying_a_dtd_would_be_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from oscal_validate import metaschema

    class _Handle(io.BytesIO):
        def __enter__(self) -> _Handle:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    class _Path:
        def open(self, mode: str) -> _Handle:
            return _Handle(b'<!DOCTYPE lolz [<!ENTITY a "boom">]><METASCHEMA/>')

    class _Files:
        def joinpath(self, *args: str) -> _Path:
            return _Path()

    monkeypatch.setattr(resources, "files", lambda _package: _Files())
    with pytest.raises(ValueError, match="refuses to parse"):
        metaschema.read_module_bytes("anything.xml")
