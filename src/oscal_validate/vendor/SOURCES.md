# Vendored specification files

These files are unmodified copies of NIST's published OSCAL 1.2.3 release
artifacts. They are the only source of structural rules, datatype patterns, and
constraints in this tool. Nothing is encoded from memory.

All fourteen were retrieved on 2026-08-14 with plain HTTP GET from the OSCAL
v1.2.3 release, `https://github.com/usnistgov/OSCAL/releases/tag/v1.2.3`
(published 2026-08-07). Each file's source URL is
`https://github.com/usnistgov/OSCAL/releases/download/v1.2.3/<original name>`;
`complete_schema.json` is `oscal_complete_schema.json` renamed on the way in,
and nothing else was changed.

| File | Original name | SHA-256 |
|---|---|---|
| `oscal/complete_schema.json` | `oscal_complete_schema.json` | `384324105c7a817af0f65b120a963146caa0e0d55d969cf0daf60e063b87a206` |
| `oscal/oscal_assessment-common_metaschema_RESOLVED.xml` | same | `260b8163dabea22199ea8c342298adabe5b8effa7ad955657f0066c62fbe9660` |
| `oscal/oscal_assessment-plan_metaschema_RESOLVED.xml` | same | `5505756506e60028d5e755fd926980763dc7a15c49e1ce09c1e4ee7f82200651` |
| `oscal/oscal_assessment-results_metaschema_RESOLVED.xml` | same | `51a0960f2344a704af93c41361cfe340b8983f25abc291a461af4f727db767ac` |
| `oscal/oscal_catalog_metaschema_RESOLVED.xml` | same | `775f8326e3dac336be17c4f7eefa89661053230fb1e8538364186c927ee062b1` |
| `oscal/oscal_component_metaschema_RESOLVED.xml` | same | `86a91b71538bb59161b41e6394282d3983c2ad049923a3aea70d2f034c86138c` |
| `oscal/oscal_control-common_metaschema_RESOLVED.xml` | same | `211517a6f94c9cba6644f2e0956986af0a5d36cf893259b1635b73dd6bd06542` |
| `oscal/oscal_implementation-common_metaschema_RESOLVED.xml` | same | `3ea7b81bd48111fade0c1c7159bba192123f31c7f7d85dfcbee7c84cfb3b3870` |
| `oscal/oscal_mapping_metaschema_RESOLVED.xml` | same | `07e4df2c0bf05750bd9b359debd5fd5d5d7f1635c867bcd9bd1e55cb5afc0754` |
| `oscal/oscal_mapping-common_metaschema_RESOLVED.xml` | same | `ab036cd28543112c0bd5ad6def844b37e0a65d00b0a6a19b1cf1ede33431fea0` |
| `oscal/oscal_metadata_metaschema_RESOLVED.xml` | same | `3d41842502a36c95554c281c79d0c2d533e4e956f0409b36cdede7001cec1b22` |
| `oscal/oscal_poam_metaschema_RESOLVED.xml` | same | `bc8a90496eb9d762c6cb5dc3f18e252236ffbbc16e544f761ae4a12039d05e13` |
| `oscal/oscal_profile_metaschema_RESOLVED.xml` | same | `ecef5ed68d793c59d2b659633e1c30633ee077e7d76f9894551ef06cadb083d9` |
| `oscal/oscal_ssp_metaschema_RESOLVED.xml` | same | `2ffc8504bffe8f5dd7f2f689f48f308bf062950abeb438ddba9a89ca03a70ffe` |

`tests/test_vendor_integrity.py` recomputes every hash on every run and checks
it against both the file and this table.

## Why both the schema and the metaschema

The JSON Schema expresses shape and datatypes. It expresses no uniqueness and
no referential integrity: checked against the vendored 1.2.3 schema,
`uniqueItems`, `const`, `if`, `not`, and `dependentRequired` appear zero times,
and the string "unique within" appears zero times. Those rules exist, and NIST
publishes them, in the Metaschema constraint layer that ships in the
`*_metaschema_RESOLVED.xml` files. Both layers are vendored because a tool that
read only the first would be checking the smaller half of the specification.

## Prose sources, cited but not vendored

These are HTML pages that carry their own "last updated" date. The exact
sentences relied on are quoted in `oscal_validate/rules.py`.

- NIST, "Identifier Use and UUIDs",
  <https://pages.nist.gov/OSCAL/learn/concepts/identifier-use/> (page last
  updated 2025-06-10, retrieved 2026-08-14). Defines locally-unique versus
  globally-unique identifiers, states that OSCAL's machine-oriented UUID
  identifiers are always globally unique, and defines instance versus
  cross-instance identifier scope.
- NIST, "URI Usage", <https://pages.nist.gov/OSCAL/learn/concepts/uri-use/>
  (page last updated 2025-03-03, retrieved 2026-08-14). Defines the bare `#`
  fragment reference and the *effective data model* a reference may reach.
- NIST, Metaschema specification, "Constraints",
  <https://pages.nist.gov/metaschema/specification/syntax/constraints/>
  (retrieved 2026-08-14). Defines `index`, `index-has-key`, `is-unique`, and
  `has-cardinality`, including that an index requires each entry to be unique
  on its composite key and that a key-field selecting nothing contributes a
  null.

## Refreshing

Re-download the fourteen files from a newer OSCAL release, update the hashes
and the release version here and in `oscal_validate/rules.py`, regenerate
`docs/CONSTRAINT-COVERAGE.md` with `make coverage-doc`, and re-run the suite. A
release can change which findings this tool emits; that is by design, and the
diff is meant to be reviewable.

## Attribution

OSCAL is a product of the National Institute of Standards and Technology. The
`usnistgov/OSCAL` repository states that, as a work of the United States
government, the project is in the public domain within the United States, and
additionally waives copyright worldwide under CC0 1.0 Universal. This project
is not affiliated with, endorsed by, or reviewed by NIST, FedRAMP, or
StateRAMP.
