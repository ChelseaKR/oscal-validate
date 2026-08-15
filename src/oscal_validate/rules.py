"""Rule citations.

Every finding this tool emits cites one of these rules, and every rule quotes a
specific published source with its URL and the date that text was retrieved. No
constraint is encoded from memory. The machine-readable source is vendored in
``oscal_validate/vendor/`` with its SHA-256 recorded in SOURCES.md; the prose
sources are NIST's own OSCAL documentation pages, quoted here rather than
vendored because they are HTML pages that carry their own "last updated" date.
"""

from __future__ import annotations

from .findings import Rule

#: The date every source below was retrieved.
RETRIEVED = "2026-08-14"

#: The OSCAL release the vendored schema snapshot is from.
OSCAL_RELEASE = "1.2.3"

SCHEMA_URL = (
    "https://github.com/usnistgov/OSCAL/releases/download/v1.2.3/oscal_complete_schema.json"
)
IDENTIFIER_USE_URL = "https://pages.nist.gov/OSCAL/learn/concepts/identifier-use/"
URI_USE_URL = "https://pages.nist.gov/OSCAL/learn/concepts/uri-use/"

_SNAPSHOT = f"the vendored oscal_complete_schema.json for OSCAL {OSCAL_RELEASE}"


def required_property_rule(assembly: str, name: str) -> Rule:
    return Rule(
        citation=(
            f'The schema declares "{name}" in the required list of {assembly} in {_SNAPSHOT}. '
            "A document missing it does not conform to the model it declares itself to be."
        ),
        url=SCHEMA_URL,
        retrieved=RETRIEVED,
    )


def undeclared_property_rule(assembly: str, name: str) -> Rule:
    return Rule(
        citation=(
            f'{assembly} sets "additionalProperties": false in {_SNAPSHOT} and does not '
            f'declare a property named "{name}". The schema permits no other properties '
            "there, so this one cannot be read as OSCAL."
        ),
        url=SCHEMA_URL,
        retrieved=RETRIEVED,
    )


def no_alternative_rule(assembly: str) -> Rule:
    return Rule(
        citation=(
            f"{assembly} is declared in {_SNAPSHOT} as a choice between alternatives, each "
            "with its own required and permitted properties. This object satisfies none of "
            "them, so no alternative in the published schema describes it."
        ),
        url=SCHEMA_URL,
        retrieved=RETRIEVED,
    )


def type_rule(assembly: str, declared: str) -> Rule:
    return Rule(
        citation=(
            f'{assembly} is declared with "type": "{declared}" in {_SNAPSHOT}, and the '
            "value found here is of a different JSON type."
        ),
        url=SCHEMA_URL,
        retrieved=RETRIEVED,
    )


def datatype_rule(datatype: str, description: str, pattern: str) -> Rule:
    return Rule(
        citation=(
            f'{datatype} in {_SNAPSHOT}: "{description}" It declares the pattern '
            f"{pattern} , and this value does not match it."
        ),
        url=SCHEMA_URL,
        retrieved=RETRIEVED,
    )


UNCOMPILABLE_PATTERN = Rule(
    citation=(
        "oscal-validate policy: the schema declares a regular expression this tool cannot "
        "compile, because JSON Schema patterns are ECMA-262 regular expressions and Python's "
        "re module does not implement the Unicode property escapes ECMA-262 allows. Values "
        "governed by such a pattern are reported as unchecked rather than approximated with "
        "a hand-written substitute, which would be a rule encoded from memory."
    ),
    url="README.md (Limits)",
    retrieved="-",
)

UUID_GLOBALLY_UNIQUE = Rule(
    citation=(
        'NIST, "Identifier Use and UUIDs", section Uniqueness (page last updated 2025-06-10): '
        '"OSCAL identifier uniqueness is categorized as locally-unique or globally-unique. '
        "As implied by the category name, locally-unique identifiers must be unique within "
        "the current document, whereas globally-unique identifiers are guaranteed to be "
        "unique across all other identifiers. OSCAL's machine-oriented UUID identifiers are "
        'always globally-unique." Two objects in one document carrying the same UUID cannot '
        "both hold."
    ),
    url=IDENTIFIER_USE_URL,
    retrieved=RETRIEVED,
)

EFFECTIVE_DATA_MODEL = Rule(
    citation=(
        'NIST, "URI Usage", section Linking to another OSCAL object (page last updated '
        '2025-03-03): a reference "uses a relative reference consisting of only a URI '
        "fragment containing the identifier or UUID of the referenced object within the "
        "current documents effective data model. The effective data model of a document "
        "includes all objects identified with the document and any directly or transitively "
        'imported documents."'
    ),
    url=URI_USE_URL,
    retrieved=RETRIEVED,
)

CROSS_INSTANCE_SCOPE = Rule(
    citation=(
        'NIST, "Identifier Use and UUIDs", section Scope (page last updated 2025-06-10): '
        '"since OSCAL supports composition relationships, there are many cases where '
        "identifiers in a source OSCAL instance need to be referenced from other OSCAL "
        'instances. These are considered cross-instance scoped identifier references." '
        "Where an imported document has not been supplied to this tool, a reference that "
        "does not resolve locally may be perfectly valid, and nothing here can settle it."
    ),
    url=IDENTIFIER_USE_URL,
    retrieved=RETRIEVED,
)

NOT_WALKED_POLICY = Rule(
    citation=(
        "oscal-validate policy: where the published schema combines alternatives in a form "
        "this tool does not resolve, the subtree is left unread and reported. An unread "
        "subtree is not a clean one, and the two are never merged in the output."
    ),
    url="README.md (Limits)",
    retrieved="-",
)

OSCAL_VERSION_FIELD = Rule(
    citation=(
        f'The schema declares metadata/oscal-version in {_SNAPSHOT} as "The OSCAL model '
        'version the document was authored against and will conform to as valid." This tool '
        f"judges every document against the vendored OSCAL {OSCAL_RELEASE} schema, whatever "
        "release the document names."
    ),
    url=SCHEMA_URL,
    retrieved=RETRIEVED,
)
