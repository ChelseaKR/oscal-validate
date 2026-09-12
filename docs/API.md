# Public API

Two surfaces are public: the JSON report, and the names exported from
`oscal_validate`. Everything else — every other module, function, class and
attribute — is internal, and may be renamed or removed in any release without
notice.

`tests/test_public_api.py` pins the names and their signatures, and
`tests/test_report_schema.py` pins the report shape, so changing either is a
deliberate act with a red suite in front of it.

## The report

`oscal-validate <file> --format json` writes a document that conforms to
[`report.schema.json`](../src/oscal_validate/report.schema.json), shipped as
package data and printed by `oscal-validate --report-schema`.

Every report carries `report_schema_version`. It is the version of the report
shape, **not** of the tool, and the two move independently:

| Change | Version part |
|---|---|
| A key is removed or renamed, a type changes, or a key that was always present becomes optional | major |
| A key is added that an existing consumer may ignore | minor |
| Only the schema's own prose changes | patch |

The schema sets `additionalProperties: false` throughout. That is on purpose:
a consumer that validates its input learns about a new key instead of passing
over it.

### What a consumer must not do

### `line` and `column`

`--locations` adds `line` and `column` to every finding. They are three-valued
and the third value matters:

| | meaning |
|---|---|
| the keys are **absent** | `--locations` was not given; the run makes no claim about where anything is |
| an **integer** | the 1-based line or column where the pointed-at value begins in the source |
| **`null`** | `--locations` was given and this run has no position for that pointer — a value the walk synthesised, or a document whose source it did not index |

They are never `0`. There is no line 0 and no column 0, so a consumer never
has to decide whether a zero is a position or an absence. `column` counts
characters; a line containing a character outside the Basic Multilingual Plane
is one column per character and more than one byte per column.

`location` remains the primary key of a finding. A position is added beside
it and never in place of it: `--diff`, `--baseline` and `tests/golden/` all
key on the pointer, which does not move when the file is reformatted.

Do not read a count with a default:

```python
errors = report["summary"].get("ERROR", 0)  # NO
errors = report["summary"]["ERROR"]  # yes
```

Every severity is always present, including the ones that are zero, precisely
so that a missing key is a broken report rather than a count of none. Reading
it with a default turns a contract change into a silently clean gate.
`tools/action_runner.py` did exactly that until 2026-09-06; it now refuses a
report it cannot fully read, and exits 2.

## The library

```python
import oscal_validate

findings = oscal_validate.validate_file(Path("ssp.json"), [Path("catalog.json")])
```

| Name | Signature | What it is |
|---|---|---|
| `validate_file` | `(document: Path, resolve: list[Path] \| None = None, *, suggest: bool = False, locations: bool = False) -> list[Finding]` | Build a session and validate in one call. The usual entry point. |
| `build_session` | `(document: Path, resolve: list[Path] \| None = None, *, suggest: bool = False, locations: bool = False) -> Session` | The loaded schema, metaschema and corpus for one run. Use it when you need the effective data model as well as the findings. |
| `validate` | `(session: Session) -> list[Finding]` | Run every check over a session. Findings come back deduplicated and in a deterministic order. |
| `Finding` | frozen dataclass | One finding: `code`, `severity`, `location`, `prop`, `value`, `message`, `rule`, `suggestions`, `acknowledged`, `position`. Its `gates` property is `True` for an ERROR nothing acknowledged, and that is the only thing the exit code is derived from. |
| `Rule` | frozen dataclass | The published rule a finding is made under: `citation`, `url`, `retrieved`. |
| `Position` | frozen dataclass | Where a finding's pointer points in the source: `file`, and a 1-based `line` and `column`. Built only under `--locations` (`locations=True`). `Finding.position` is `None` when the run built no index *or* when the pointer names nothing in the source, and neither is a position — the report prints words, never a zero. `column` counts characters, not UTF-8 bytes. |
| `Acknowledgement` | frozen dataclass | Why a `--baseline` entry accepted a finding, and when: `reason`, `acknowledged_on`. `Finding.acknowledged` is `None` when nothing acknowledged it, and `None` is not a neutral value — it is what makes an ERROR gate. |
| `Severity` | `StrEnum` | `ERROR`, `WARNING`, `INFO`, `UNVERIFIABLE`. |
| `REPORT_SCHEMA_VERSION` | `str` | The version of the report schema this package writes. |
| `read_report_schema` | `() -> str` | The schema as published, byte for byte. |
| `__version__` | `str` | The tool's version. |

`Session` is returned by `build_session` and consumed by `validate`. It is
public as a value — hold it, pass it back — but its fields are not part of this
promise.

### Stability

The package follows Semantic Versioning. Within a major version:

- no name in the table above is removed or renamed;
- no parameter is removed, reordered, or made required;
- `Finding`, `Rule`, `Acknowledgement` and `Position` gain no required field,
  and lose no field. `Finding` may gain an optional one, as it did with
  `suggestions` (0.3.0), `acknowledged` (0.5.0) and `position`; a consumer
  that constructs a `Finding` by keyword is unaffected, and one that compares
  two by equality should know that an optional field is part of that
  comparison;
- `Severity` may gain a member. A consumer that switches on severity should
  have a branch for one it does not know, and must not treat an unknown
  severity as a pass.

A change to any of the above is a major release, listed in the CHANGELOG under
`Changed` or `Removed` before it ships.

### What is deliberately not promised

- The text output. It is for people, and its layout may change in any release;
  parse `--format json`.
- Exit codes are the CLI's contract, not the library's: 0 no ERROR findings
  that a `--baseline` did not acknowledge, 1 at least one of those or a stale
  baseline entry under `--fail-on-stale`, 2 the input or the baseline could
  not be read. Those are stable.
- Finding `message` strings. The `code` is the stable identifier; the message
  is prose and may be reworded to say the same thing better.
