"""The boundary, enforced without a model.

The README's founding limit is that this tool cannot tell you whether a
control is implemented, whether a system is secure, or whether a package
would be authorized. The model-backed commands are instructed to refuse
those questions; this module is the check that does not depend on the
instruction being followed. Every sentence that will be shown to a reader
passes through ``screen``; a sentence carrying an implementation, security,
or authorization judgment is withheld and counted, and the reader sees that
it was.

The patterns err toward withholding. A sentence that says "this control is
implemented" is a judgment; so is "the system appears secure" and "this
package is FedRAMP-ready". A sentence that says the tool *cannot* judge
those things is the boundary being stated, and is kept. The test of which
is which is lexical, on purpose: a guard that asked a model whether the
model had overstepped would be no guard at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Things a judgment is about. Matched after a copula or evaluative verb.
_OBJECTS = (
    r"(?:fully |partially |properly |adequately |correctly |effectively |not |un)?"
    r"(?:implemented|unimplemented|secure|insecure|safe|unsafe|compliant|non-?compliant|"
    r"authorized|unauthorized|authorizable|accredited|certified|"
    r"fedramp[- ]ready|ato[- ]ready|audit[- ]ready|ready for (?:an? )?(?:ato|authorization|"
    r"fedramp|stateramp|assessment|submission)|"
    r"sufficient|insufficient|adequate|inadequate|effective|ineffective|"
    r"good enough|acceptable|unacceptable|satisfactory|unsatisfactory|"
    r"in place|operating effectively|met|unmet|satisfied|addressed|covered)"
)

_COPULA = (
    r"\b(?:is|are|was|were|has been|have been|appears?|seems?|looks?|remains?|"
    r"would be|will be|should be|could be|can be|must be|may be|is considered|"
    r"are considered|is deemed|are deemed|is likely|are likely|is probably|are probably|"
    r"is clearly|are clearly|is now|are now)\s+(?:\w+\s+){0,2}?"
)

_JUDGMENT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        _COPULA + _OBJECTS + r"\b",
        # "satisfies AC-2", "meets the requirements of", "fails to meet", "complies with"
        r"\b(?:satisf(?:y|ies|ied)|meets?|fulfil(?:l|ls|led)?s?|complies with|comply with|"
        r"fails? to (?:meet|satisfy|implement|comply)|does not (?:meet|satisfy|comply|implement)|"
        r"do not (?:meet|satisfy|comply|implement)|violates?|conforms? to|adheres? to)\s+"
        r"(?:the |all |every |its |their )?(?:requirements? (?:of |for |in )?|intent of |"
        r"control |controls |baseline |standard |"
        r"[a-z]{2,3}-\d+(?:\.\d+|\(\d+\))?|nist|fedramp|stateramp|sp ?800-\d+|cmmc|iso ?\d+|"
        r"hipaa|pci|soc ?2)",
        # "would pass / receive / be granted / get an ATO or authorization"
        r"\b(?:would|will|should|could|can|may|might|likely to|going to|able to)\s+"
        r"(?:pass|receive|obtain|get|be granted|be awarded|achieve|earn|secure|qualify for)\s+"
        r"(?:an? |the |its |their )?(?:ato|authorization|authorisation|fedramp|stateramp|"
        r"accreditation|certification|approval|authority to operate)",
        # "the risk is low/acceptable", "poses no risk", "no vulnerabilities"
        r"\b(?:risk|residual risk|security posture|exposure)\s+(?:is|are|remains?|appears?|"
        r"seems?|looks?)\s+(?:\w+\s+)?(?:low|high|medium|moderate|minimal|negligible|"
        r"acceptable|unacceptable|elevated|significant|manageable|well[- ]managed|sound|"
        r"strong|weak|poor|good)\b",
        r"\b(?:poses?|presents?|carries|has|have|contains?)\s+(?:no|zero|little|minimal|"
        r"significant|serious|major|critical)\s+(?:security )?(?:risk|vulnerabilit|weakness|"
        r"exposure|gap)",
        # recommendations to grant, approve, accept, sign off
        r"\b(?:i |we )?(?:recommend|suggest|advise|endorse)\s+(?:that (?:you |the \w+ )?)?"
        r"(?:approv|grant|accept|authoriz|authoris|sign(?:ing)? off|certif|accredit)",
        # "this SSP / system / package is ready", "ready to submit"
        r"\b(?:ssp|system|package|plan|poa&m|poam|implementation|environment|organization|"
        r"organisation|it|this|that|they|these|those)\s+(?:is|are|looks?|appears?|seems?)\s+"
        r"(?:\w+\s+)?ready\b",
        r"\bready (?:to|for) (?:submit|submission|authorization|authorisation|an ato|ato|"
        r"fedramp|stateramp|assessment|audit|approval)\b",
        r"\b(?:passes|passed|would pass|will pass|clears|cleared)\s+(?:an? |the )?"
        r"(?:assessment|audit|3pao|review|fedramp|stateramp|authorization|security review)",
        r"\b(?:control|requirement|safeguard|countermeasure)s?\s+(?:is|are|has been|have been)"
        r"\s+(?:fully |partially |properly |not )?(?:implemented|in place|operating|satisfied|"
        r"met|addressed|covered|effective)\b",
    )
)

#: A sentence carrying one of these is the boundary being stated, not crossed.
_REFUSAL_MARKERS = re.compile(
    r"\b(?:cannot|can't|can not|could not|couldn't|unable|not able|does not|doesn't|do not|"
    r"don't|did not|didn't|never|no way to|not possible|impossible|not something|"
    r"not a question|not evidence|is not the same as|says nothing|tells? you nothing|"
    r"means nothing|outside (?:of )?(?:what|the scope|this tool|its scope)|out of scope|"
    r"beyond (?:what|the scope|this tool)|would (?:take|require|need|call for)|"
    r"only (?:a|an) (?:qualified|independent|human|trained|licensed|accredited|authoriz)|"
    r"for (?:a|an|the|your|its) (?:\w+ ){0,2}(?:assessor|assessors|official|officials|auditor|"
    r"auditors|3pao|reviewer|reviewers|human|person|team|authority) to|"
    r"structural conformance|not (?:judge|assess|determine|evaluate|"
    r"decide|confirm|tell|say|know|answer|speak|claim|state|conclude)|"
    r"refuse|declin|won't|will not|no opinion|not in a position|"
    r"whether|question of|asks? (?:whether|if)|is asking|you(?:'re| are) asking)\b",
    re.IGNORECASE,
)

#: The sentence shown in place of one that was withheld.
WITHHELD = "[withheld: a judgment about implementation, security, or authorization]"

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\[\"'(*\-\d])")


@dataclass(frozen=True)
class Screened:
    text: str
    withheld: tuple[str, ...]

    @property
    def withheld_count(self) -> int:
        return len(self.withheld)


def is_judgment(sentence: str) -> bool:
    """True when the sentence asserts an implementation, security, or authorization verdict."""
    if not any(pattern.search(sentence) for pattern in _JUDGMENT_PATTERNS):
        return False
    return _REFUSAL_MARKERS.search(sentence) is None


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text) if s]


def screen(text: str) -> Screened:
    """Withhold every sentence that crosses the boundary; keep the rest verbatim.

    Paragraph structure is preserved: splitting happens within each line, so
    a withheld sentence is replaced in place and nothing else moves.
    """
    withheld: list[str] = []
    lines: list[str] = []
    for line in text.split("\n"):
        kept: list[str] = []
        for sentence in split_sentences(line):
            if is_judgment(sentence):
                withheld.append(sentence.strip())
                kept.append(WITHHELD)
            else:
                kept.append(sentence)
        lines.append(" ".join(kept) if kept else line)
    return Screened(text="\n".join(lines), withheld=tuple(withheld))


def screen_values(values: list[str]) -> Screened:
    """The same screen over a list of short strings, such as patch values."""
    withheld: list[str] = []
    kept: list[str] = []
    for value in values:
        result = screen(value)
        withheld.extend(result.withheld)
        kept.append(result.text)
    return Screened(text="\n".join(kept), withheld=tuple(withheld))
