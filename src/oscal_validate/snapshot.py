"""The identity of the vendored OSCAL snapshot, taken from the bytes it reads.

Every finding this tool emits is a claim about a specific published release of
OSCAL, and the whole of what it knows about that release is a set of files
vendored under ``vendor/oscal/``. ``vendor/SOURCES.md`` records where each one
came from and its SHA-256, and ``tests/test_vendor_integrity.py`` fails if a
vendored file ever stops matching the hash recorded for it.

That gate protects the repository. It does not travel with a report. A SARIF
log read six months later in someone else's code-scanning dashboard says
"oscal-validate 0.2.0 found this", and the reader has no way to tell which
bytes decided it -- so a re-vendoring that changes a verdict is invisible at
exactly the place the verdict is read.

So the digests are computed here, at run time, from the files the tool
actually opens, and travel in the SARIF log's ``tool.driver.properties``.

Two properties of that are deliberate:

**Computed, not recorded.** These are not read out of ``SOURCES.md`` or copied
from the test's table. A recorded hash answers "what did we write down"; a
computed one answers "what did this run read", which is the question a reader
of an old report is actually asking. The two agreeing is
:func:`tests.test_vendor_integrity` and
``tests/test_sarif.py::test_the_driver_digests_are_the_recorded_snapshot_hashes``;
if they ever disagree, the recorded one is the one that is wrong.

**Complete, or it is not an identity.** :data:`VENDORED_FILES` must name every
file under ``vendor/oscal/``, and a test asserts that against the directory
itself. A snapshot identity that silently omits a file is worse than none: it
looks like a full fingerprint while a changed metaschema module passes under
it unnoticed, which is this repository's own dominant defect -- an absence
published as a measurement.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from importlib import resources

from .metaschema import MODULES
from .rules import OSCAL_RELEASE
from .schema import VENDORED_SCHEMA

#: The hash algorithm the digests are taken with, named in the output so a
#: reader never has to infer it from a hex string's length.
ALGORITHM = "sha256"

#: Every vendored file the tool reads, as a path relative to ``vendor/``.
#: ``tests/test_sarif.py`` asserts this is the whole of ``vendor/oscal/``.
VENDORED_FILES: tuple[str, ...] = (
    VENDORED_SCHEMA,
    *(f"oscal/{module}" for module in MODULES),
)


def _read(relpath: str) -> bytes:
    path = resources.files("oscal_validate").joinpath("vendor").joinpath(relpath)
    with path.open("rb") as handle:
        data: bytes = handle.read()
    return data


@lru_cache(maxsize=1)
def digests() -> dict[str, str]:
    """``{relative path: hex digest}`` for every vendored file, computed now.

    Cached, because the files cannot change under a running process and the
    schema alone is several megabytes; the cache is on the whole mapping, so
    there is no partial state to read.
    """
    return {relpath: hashlib.sha256(_read(relpath)).hexdigest() for relpath in VENDORED_FILES}


def identity() -> dict[str, object]:
    """The snapshot's identity, as a SARIF property bag.

    ``release`` is the OSCAL release the snapshot is from, which is what a
    human reads; ``files`` is what a machine checks it against.
    """
    return {
        "release": OSCAL_RELEASE,
        "algorithm": ALGORITHM,
        "files": dict(sorted(digests().items())),
    }
