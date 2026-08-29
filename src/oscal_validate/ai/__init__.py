"""Model-backed commands, at the edges of a validator that does not change.

Nothing in ``oscal_validate`` outside this package imports it, and nothing in
it produces a finding. The four commands here -- ``explain``, ``repair
--draft``, ``walkthrough``, and ``ask`` -- start from the deterministic
validator's findings and from NIST's published text, and every sentence they
show has been through two checks that do not involve a model: the quote
verifier (``verify.py``) and the boundary guard (``guard.py``).

The SDK is imported lazily, inside the code that needs it, so that the
default command stays importable and runnable without it. ADR-0005 records
the decision; ``tests/test_offline_guarantee.py`` and
``tests/test_default_path_byte_identity.py`` enforce the separation.
"""

from __future__ import annotations

#: Bumped whenever any prompt text changes. Recorded in every eval result so a
#: number can be tied to the exact wording that produced it.
PROMPT_VERSION = "2026-08-29.1"

__all__ = ["PROMPT_VERSION"]
