# Fixtures

| File | What it is | Provenance |
|---|---|---|
| `clean_catalog.json` | A synthetic catalog proven clean by the validator | Written for this repository |
| `clean_profile.json` | A synthetic profile importing a catalog it is not given | Written for this repository |
| `clean_mapping_collection.json` | A synthetic mapping collection proven clean by the validator, and the baseline every seeded corruption inside a mapping starts from | Written for this repository |
| `broken_catalog.json` | `clean_catalog.json` with `metadata/last-modified` removed and the second control's `id` duplicated; three ERROR findings | Derived here, 2026-08-21 |
| `nist_ssp_example.json` | NIST's published system security plan example | `https://raw.githubusercontent.com/usnistgov/oscal-content/main/examples/ssp/json/ssp-example.json`, retrieved 2026-08-14 by the survey harness (record in `docs/findings/2026-08-14-published-oscal-survey.json`), SHA-256 `af97587d6d14b0f1a297899b3f6a09b61675063f3279c7b7ffe16578f8859197`; a US government work in the public domain |
