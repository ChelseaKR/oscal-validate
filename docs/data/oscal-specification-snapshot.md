# Data card: the vendored OSCAL specification snapshot

The only source of rules this tool has. Everything it knows about OSCAL comes
out of these files; nothing is encoded from memory.

| | |
|---|---|
| Source | NIST, OSCAL v1.2.3 release, `https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3` (published 2026-08-07) |
| What is taken | `oscal_complete_schema.json` and the thirteen `*_metaschema_RESOLVED.xml` modules, unmodified |
| Retrieved | 2026-08-14, plain HTTP GET, one request per file |
| Where it lives | `src/oscal_validate/vendor/oscal/`, shipped as package data |
| Tier | L1, public and non-sensitive. No personal data, no identity content, nothing about any real system |
| Licence | Public domain in the United States as a work of the US government, with a worldwide CC0 1.0 waiver, as stated by `usnistgov/OSCAL`. Compatible with this repository's Apache-2.0 |
| Integrity | SHA-256 per file in [`../../src/oscal_validate/vendor/SOURCES.md`](../../src/oscal_validate/vendor/SOURCES.md), recomputed on every test run by `tests/test_vendor_integrity.py`, which also fails if a file appears in `vendor/` without a hash row |
| Refresh trigger | A new OSCAL release. There is no time-based cadence: the artifact is a specification snapshot, and it is correct until NIST publishes another one |
| Staleness signal | Every report names the release it judged against, and every document whose own `oscal-version` differs gets an `OSCAL_VERSION_DIFFERS` finding. There is no runtime alarm on the snapshot's own age; see the gap below |
| Retention | Indefinite. The snapshot is the product: a finding cites the bytes that produced it, so an old snapshot stays meaningful after a newer release exists. Removed within 30 days if the publisher ever revokes or relicenses |

## Known limitations

- **The snapshot has no stated freshness SLA.** Re-vendoring on a new OSCAL
  release is a REVIEW item in [`../ROADMAP.md`](../ROADMAP.md) with a human
  owner, checked manually against the OSCAL releases page. Nothing in the tool
  warns that the vendored release is old, because the tool has no clock and no
  network and adding either would cost properties that matter more.
- **XML is parsed with the standard library**, on the grounds that these files
  are hash-pinned package data no user supplies. Any vendored file carrying
  `<!DOCTYPE` or `<!ENTITY` is refused before it reaches the parser. See
  ADR-0003.
- The XML modules are the `_RESOLVED` forms NIST publishes, so module imports
  are already inlined. This tool does not resolve metaschema imports itself.
