# Which of NIST's published constraints this tool evaluates

Generated from the vendored metaschema files for OSCAL 1.2.3
(retrieved 2026-08-14) by `tools/constraint_coverage.py`. Do not edit by hand:
`make coverage-doc` regenerates it and `tests/test_constraint_coverage.py`
fails if it is stale.

This file exists because "no findings" and "every published constraint passed"
are different claims, and only the first one is ever true here. Every
constraint NIST publishes is listed below with whether this tool runs it, and
where it does not, the reason.

## Summary

78 of 340 published constraints are evaluated.

| Constraint kind | Published | Evaluated |
|---|---:|---:|
| `allowed-values` | 200 | 0 |
| `expect` | 12 | 0 |
| `has-cardinality` | 11 | 5 |
| `index` | 20 | 15 |
| `index-has-key` | 24 | 10 |
| `is-unique` | 48 | 48 |
| `matches` | 25 | 0 |
| **total** | **340** | **78** |

## Evaluated

| Constraint | Kind | Level | Declared on | Target |
|---|---|---|---|---|
| `oscal-back-matter-resource-base64-rlink-cardinality` | has-cardinality | WARNING | `resource` | `rlink|base64` |
| `oscal-by-component-export-provided-responsibility-cardinality` | has-cardinality | ERROR | `export` | `provided|responsibility` |
| `oscal-implemented-requirement-by-component-cardinality` | has-cardinality | ERROR | `implemented-requirement` | `.//by-component` |
| `oscal-metadata-location-address-cardinality` | has-cardinality | WARNING | `location` | `address` |
| `oscal-metadata-location-title-address-email-address-telephone-cardinality` | has-cardinality | ERROR | `location` | `title|address|email-address|telephone-number` |
| `oscal-back-matter-resource-uuid-index` | index | ERROR | `back-matter` | `resource` |
| `oscal-catalog-controls` | index | ERROR | `catalog` | `//control` |
| `oscal-catalog-groups` | index | ERROR | `catalog` | `//group` |
| `oscal-catalog-groups-controls-parts` | index | ERROR | `catalog` | `//(control|group|part)` |
| `oscal-catalog-params` | index | ERROR | `catalog` | `//param` |
| `oscal-catalog-parts` | index | ERROR | `catalog` | `//part` |
| `oscal-catalog-props` | index | ERROR | `catalog` | `//prop` |
| `oscal-index-metadata-location-uuid` | index | ERROR | `metadata` | `location` |
| `oscal-index-metadata-party-uuid` | index | ERROR | `metadata` | `party` |
| `oscal-index-metadata-property-uuid` | index | ERROR | `metadata` | `.//prop` |
| `oscal-index-metadata-role-id` | index | ERROR | `metadata` | `role` |
| `oscal-index-metadata-roles` | index | ERROR | `metadata` | `role` |
| `oscal-index-system-component-uuid` | index | ERROR | `component-definition` | `component` |
| `oscal-system-implementation-component-leveraged-authorization-uuid-index` | index | ERROR | `system-implementation` | `leveraged-authorization` |
| `oscal-system-implementation-component-uuid-index` | index | ERROR | `system-implementation` | `component` |
| `oscal-by-component-export-provided-uuid-index` | index-has-key | ERROR | `export` | `responsibility` |
| `oscal-index-inventory-item-responsible-party-party-uuid` | index-has-key | ERROR | `inventory-item` | `responsible-party` |
| `oscal-index-inventory-item-responsible-party-role-id` | index-has-key | ERROR | `inventory-item` | `responsible-party` |
| `oscal-index-metadata-location-uuid` | index-has-key | ERROR | `location-uuid` | `.` |
| `oscal-index-metadata-party-organizations-uuid` | index-has-key | ERROR | `member-of-organization` | `.` |
| `oscal-index-metadata-party-uuid` | index-has-key | ERROR | `party-uuid` | `.` |
| `oscal-index-metadata-role-id` | index-has-key | ERROR | `role-id` | `.` |
| `oscal-metadata-action-name-index-metadata-party-uuid` | index-has-key | ERROR | `action` | `responsible-party` |
| `oscal-metadata-action-name-index-metadata-role-id` | index-has-key | ERROR | `action` | `responsible-party` |
| `oscal-metadata-responsible-party-index-metadata-role-id` | index-has-key | ERROR | `responsible-party` | `.` |
| `oscal-metadata-unique-document-id` | is-unique | ERROR | `metadata` | `document-id` |
| `oscal-unique-activity-responsible-role` | is-unique | ERROR | `activity` | `responsible-role` |
| `oscal-unique-ap-local-definitions-component` | is-unique | ERROR | `local-definitions` | `component` |
| `oscal-unique-ap-local-definitions-user` | is-unique | ERROR | `local-definitions` | `user` |
| `oscal-unique-ar-attestation-responsible-party` | is-unique | ERROR | `attestation` | `responsible-party` |
| `oscal-unique-ar-local-definitions-component` | is-unique | ERROR | `local-definitions` | `component` |
| `oscal-unique-ar-local-definitions-user` | is-unique | ERROR | `local-definitions` | `user` |
| `oscal-unique-associated-activity-responsible-role` | is-unique | ERROR | `associated-activity` | `responsible-role` |
| `oscal-unique-component-definition-capability` | is-unique | ERROR | `component-definition` | `capability` |
| `oscal-unique-component-definition-capability-incorporates-component` | is-unique | ERROR | `capability` | `incorporates-component` |
| `oscal-unique-component-definition-control-implementation-set-parameter` | is-unique | ERROR | `control-implementation` | `set-parameter` |
| `oscal-unique-component-definition-implemented-requirement-responsible-role` | is-unique | ERROR | `implemented-requirement` | `responsible-role` |
| `oscal-unique-component-definition-implemented-requirement-set-parameter` | is-unique | ERROR | `implemented-requirement` | `set-parameter` |
| `oscal-unique-component-definition-implemented-requirement-statement` | is-unique | ERROR | `implemented-requirement` | `statement` |
| `oscal-unique-component-definition-statement-responsible-role` | is-unique | ERROR | `statement` | `responsible-role` |
| `oscal-unique-defined-component-responsible-role` | is-unique | ERROR | `defined-component` | `responsible-role` |
| `oscal-unique-implemented-component-responsible-party` | is-unique | ERROR | `implemented-component` | `responsible-party` |
| `oscal-unique-inherited-responsible-role` | is-unique | ERROR | `inherited` | `responsible-role` |
| `oscal-unique-inventory-item-responsible-party` | is-unique | ERROR | `inventory-item` | `responsible-party` |
| `oscal-unique-metadata-doc-id` | is-unique | ERROR | `metadata` | `document-id` |
| `oscal-unique-metadata-link` | is-unique | WARNING | `metadata` | `link` |
| `oscal-unique-metadata-property` | is-unique | ERROR | `metadata` | `prop` |
| `oscal-unique-metadata-responsible-party` | is-unique | ERROR | `metadata` | `responsible-party` |
| `oscal-unique-poam-local-definitions-component` | is-unique | ERROR | `local-definitions` | `component` |
| `oscal-unique-profile-modify-set-parameter` | is-unique | ERROR | `modify` | `set-parameter` |
| `oscal-unique-provided-responsible-role` | is-unique | ERROR | `provided` | `responsible-role` |
| `oscal-unique-resource-base64-filename` | is-unique | ERROR | `resource` | `base64` |
| `oscal-unique-resource-rlink-href` | is-unique | ERROR | `resource` | `rlink` |
| `oscal-unique-responsibility-responsible-role` | is-unique | ERROR | `responsibility` | `responsible-role` |
| `oscal-unique-satisfied-responsible-role` | is-unique | ERROR | `satisfied` | `responsible-role` |
| `oscal-unique-ssp-assessment-assets-component` | is-unique | ERROR | `assessment-assets` | `component` |
| `oscal-unique-ssp-authorization-boundary-diagram` | is-unique | ERROR | `authorization-boundary` | `diagram` |
| `oscal-unique-ssp-by-component-set-parameter` | is-unique | ERROR | `by-component` | `set-parameter` |
| `oscal-unique-ssp-control-implementation-set-parameter` | is-unique | ERROR | `control-implementation` | `set-parameter` |
| `oscal-unique-ssp-data-flow-diagram` | is-unique | ERROR | `data-flow` | `diagram` |
| `oscal-unique-ssp-implemented-requirement-by-component` | is-unique | ERROR | `implemented-requirement` | `by-component` |
| `oscal-unique-ssp-implemented-requirement-responsible-role` | is-unique | ERROR | `implemented-requirement` | `responsible-role` |
| `oscal-unique-ssp-implemented-requirement-set-parameter` | is-unique | ERROR | `implemented-requirement` | `set-parameter` |
| `oscal-unique-ssp-implemented-requirement-statement` | is-unique | ERROR | `implemented-requirement` | `statement` |
| `oscal-unique-ssp-implemented-requirement-statement-by-component` | is-unique | ERROR | `statement` | `by-component` |
| `oscal-unique-ssp-network-architecture-diagram` | is-unique | ERROR | `network-architecture` | `diagram` |
| `oscal-unique-ssp-related-task-responsible-party` | is-unique | ERROR | `related-task` | `responsible-party` |
| `oscal-unique-ssp-statement-responsible-role` | is-unique | ERROR | `statement` | `responsible-role` |
| `oscal-unique-ssp-system-characteristics-responsible-party` | is-unique | ERROR | `system-characteristics` | `responsible-party` |
| `oscal-unique-ssp-system-implementation-user` | is-unique | ERROR | `system-implementation` | `user` |
| `oscal-unique-ssp-uses-component-responsible-party` | is-unique | ERROR | `uses-component` | `responsible-party` |
| `oscal-unique-step-responsible-role` | is-unique | ERROR | `step` | `responsible-role` |
| `oscal-unique-system-component-responsible-role` | is-unique | ERROR | `system-component` | `responsible-role` |

## Evaluated, but reading an index that is never built

These constraints are parsed and run, and they can never produce a definite answer: the `index` constraint that would populate the index they read is one of the skipped constraints below, so every lookup misses. References checked against them are reported UNVERIFIABLE, naming the index, and are never reported as failures of the document.

| Constraint | Declared on | Reads index | Populated by |
|---|---|---|---|
| `oscal-by-component-export-provided-uuid-index` | `export` | `by-component-export-provided-uuid` | `oscal-by-component-export-provided-uuid-index`, skipped |
| `oscal-index-metadata-party-organizations-uuid` | `member-of-organization` | `index-metadata-party-organizations-uuid` | `oscal-index-metadata-party-organizations-uuid`, skipped |

## Not evaluated

Neither passed nor failed. A document that this tool reports no findings for may still violate any of these.

| Constraint | Kind | Declared on | Why not |
|---|---|---|---|
| `(unnamed)` | allowed-values | `mapping-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `mapping-resource-reference` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `qualifier-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `qualifier-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `qualifier-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `relationship` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `(unnamed)` | allowed-values | `category` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-activity-type-values` | allowed-values | `activity` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-activity-values` | allowed-values | `activity` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-alter-position-values` | allowed-values | `add` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assesment-part-objective-method-value` | allowed-values | `part` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assesment-part-objective-name` | allowed-values | `part` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assessment-objective-types` | allowed-values | `local-objective` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assessment-part-values` | allowed-values | `part` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assessment-subject-type-values` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-assessment-subject-values` | allowed-values | `assessment-subject` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-back-matter-resource-hash-algorithm-values` | allowed-values | `hash` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-back-matter-resource-prop-name-values` | allowed-values | `resource` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-back-matter-resource-prop-type-values` | allowed-values | `resource` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-by-component-link-rel-values` | allowed-values | `by-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-by-component-responsible-role-id-values` | allowed-values | `by-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-catalog-metadata-link-rel-type` | allowed-values | `catalog` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-catalog-metadata-prop-name` | allowed-values | `catalog` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-characterization-facet-name-system-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-allows-authenticated-scan-value` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-asset-type-value` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-hardware-service-software-prop-name-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-implementation-point-value` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-interconnection-link-rel-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-interconnection-prop-name-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-interconnection-responsible-role-id-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-interconnection-service-software-system-prop-name-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-inventory-item-allows-authenticated-scan-values` | allowed-values | `system-implementation` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-link-rel-type` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-link-rel-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-allows-authenticated-scan-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-asset-type-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-direction-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-implementation-point-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-ipaddress-class-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-is-public-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-is-virtual-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-name` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-name-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-prop-validation-link-rel-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-protocol-transport-values` | allowed-values | `port-range` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-public-value` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-responsible-role-id-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-role-id` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-service-link-rel-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-software-prop-name-values` | allowed-values | `system-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-status-state-values` | allowed-values | `status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-type` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-type-values` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-component-virtual-value` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-link-rel-type` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-objective-part-method-prop-value` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-objective-part-subpart-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-part-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-prop-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-prop-status-value` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-statement-part-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-statement-part-prop-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-statement-part-rmf-prop-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-control-statement-part-subpart-name` | allowed-values | `control` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-ac-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-at-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-au-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-av-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-e-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-env-cia-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-mac-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-mat-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-mav-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-mpr-mvs-cia-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-msc-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-msi-msa-cia-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-mui-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-pr-cia-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-r-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-re-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-s-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-u-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-ui-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-v-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-cvss-v4.0-vectors` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-diagram-link-rel-values` | allowed-values | `diagram` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cve-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-access-complexity-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-access-vector-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-authentication-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-cia-requirement-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-collateral-damage-potential-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-confidentiality-impact-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-exploitability-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-name-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-remediation-level-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss2-report-confidence-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-access-complexity-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-access-vector-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-cia-impact-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-cia-requirement-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-exploit-code-maturity-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-modified-attack-complexity-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-modified-attack-vector-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-modified-cia-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-modified-scope-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-modified-user-interaction-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-name-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-remediation-level` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-report-confidence-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-scope` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-cvss3-user-interaction` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-fedramp-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-name-core-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-prop-name-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-facet-prop-state-values` | allowed-values | `facet` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-finding-target-reason-values` | allowed-values | `status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-finding-target-status-state-values` | allowed-values | `status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-finding-target-values` | allowed-values | `finding-target` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-fips-199-impact-levels` | allowed-values | `system-information` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-group-part-name` | allowed-values | `group` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-group-prop-name` | allowed-values | `group` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implementation-status-values` | allowed-values | `implementation-status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implemented-component-prop-name-values` | allowed-values | `implemented-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implemented-component-responsible-party-role-id-values` | allowed-values | `implemented-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implemented-requirement-responsible-role-id-values` | allowed-values | `implemented-requirement` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implemented-requirement-statement-by-component-prop-control-origination-values` | allowed-values | `implemented-requirement` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-implemented-requirement-statement-by-component-prop-name-values` | allowed-values | `implemented-requirement` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-information-type-categorization-system-values` | allowed-values | `categorization` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-hardware-service-software-prop-name-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-link-rel-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-prop-asset-type-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-prop-is-scanned-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-prop-name-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-inventory-item-responsible-party-role-id-values` | allowed-values | `inventory-item` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-leveraged-authorization-link-rel-values` | allowed-values | `leveraged-authorization` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-mapping-coverage-generation-method-values` | allowed-values | `coverage` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-action-system-values` | allowed-values | `action` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-action-type-values` | allowed-values | `action` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-address-location-type-values` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-document-id-scheme-values` | allowed-values | `document-id` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-link-rel-values` | allowed-values | `link` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-link-rel-values` | allowed-values | `metadata` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-location-prop-name-values` | allowed-values | `location` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-location-prop-type-data-center-values` | allowed-values | `location` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-location-prop-type-values` | allowed-values | `location` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-party-external-id-values` | allowed-values | `external-id` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-party-prop-name-values` | allowed-values | `party` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-party-type-values` | allowed-values | `party` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-prop-name-values` | allowed-values | `prop` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-prop-name-values` | allowed-values | `metadata` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-responsible-party-role-ids` | allowed-values | `metadata` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-revision-link-rel-types` | allowed-values | `revision` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-metadata-telephone-number-type-values` | allowed-values | `telephone-number` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-observation-method-type-values` | allowed-values | `method` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-observation-values` | allowed-values | `type` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-origin-actor-type-values` | allowed-values | `origin-actor` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-parameter-how-many-type` | allowed-values | `parameter-selection` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-parameter-prop-name` | allowed-values | `param` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-part-prop-name` | allowed-values | `part` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-profile-alter-by-item-name-values` | allowed-values | `remove` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-profile-insert-controls-order-values` | allowed-values | `insert-controls` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-profile-merge-combine-method-values` | allowed-values | `combine` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-profile-modify-alter-prop-name-values` | allowed-values | `add` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-response-lifecycle-values` | allowed-values | `response` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-response-prop-name` | allowed-values | `response` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-response-prop-type-value` | allowed-values | `response` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-risk-prop-name-values` | allowed-values | `entry` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-risk-prop-name-values` | allowed-values | `risk` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-risk-prop-type-values` | allowed-values | `entry` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-risk-status-values` | allowed-values | `risk-status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-rmf-parameter-prop-name` | allowed-values | `param` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-service-component-link-rel-type` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-software-component-prop-name` | allowed-values | `defined-component` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-statement-responsible-role-id-values` | allowed-values | `statement` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-status-state-values` | allowed-values | `status` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-prop-cloud-deployment-model-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-prop-cloud-service-model-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-prop-name-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-prop-name-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-prop-sp-800-63-assurance-level-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-characteristics-responsible-party-role-id-values` | allowed-values | `system-characteristics` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-identifier-type-values` | allowed-values | `system-id` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-information-link-rel-values` | allowed-values | `system-information` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-information-prop-name-values` | allowed-values | `system-information` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-system-information-prop-privacy-designation-values` | allowed-values | `system-information` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-task-values` | allowed-values | `task` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-terms-and-conditions-part-name` | allowed-values | `terms-and-conditions` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-threat-id-system` | allowed-values | `threat-id` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-timing-unit-values` | allowed-values | `at-frequency` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-user-prop-name-values` | allowed-values | `system-user` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-user-prop-privilege-level-values` | allowed-values | `system-user` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-user-prop-type-values` | allowed-values | `system-user` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-user-role-id-values` | allowed-values | `system-user` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-with-child-controls-values` | allowed-values | `-` | most allowed-value sets declare allow-other, so a value outside them is not necessarily a violation |
| `oscal-back-matter-resource-citation-title` | expect | `resource` | the test is a Metapath expression, which this tool does not implement |
| `oscal-catalog-control-require-statement-when-appropriate` | expect | `control` | the test is a Metapath expression, which this tool does not implement |
| `oscal-component-protocol-port-range-has-end` | expect | `port-range` | the test is a Metapath expression, which this tool does not implement |
| `oscal-component-protocol-port-range-has-start` | expect | `port-range` | the test is a Metapath expression, which this tool does not implement |
| `oscal-component-protocol-port-range-starts-before-end` | expect | `port-range` | the test is a Metapath expression, which this tool does not implement |
| `oscal-component-protocol-uuid` | expect | `protocol` | the test is a Metapath expression, which this tool does not implement |
| `oscal-information-type-uuid` | expect | `information-type` | the test is a Metapath expression, which this tool does not implement |
| `oscal-metadata-link-uri-reference-no-media-type` | expect | `link` | the test is a Metapath expression, which this tool does not implement |
| `oscal-method-part-has-method-prop` | expect | `control` | the test is a Metapath expression, which this tool does not implement |
| `oscal-parameter-depends-on-deprecated` | expect | `param` | the test is a Metapath expression, which this tool does not implement |
| `oscal-poam-item-uuid` | expect | `poam-item` | the test is a Metapath expression, which this tool does not implement |
| `oscal-profile-req-merge-combine` | expect | `combine` | the test is a Metapath expression, which this tool does not implement |
| `oscal-activity-type-cardinality` | has-cardinality | `activity` | its target expression is outside the Metapath subset this tool parses: prop[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name='method'] |
| `oscal-assesment-part-objective-cardinality` | has-cardinality | `part` | its target expression is outside the Metapath subset this tool parses: .[@name='objective']/prop[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name='method'] |
| `oscal-assessment-method-cardinality` | has-cardinality | `local-objective` | its target expression is outside the Metapath subset this tool parses: part[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name=('assessment','assessment-method')]/prop[has-oscal-namespace(('http://csrc.nist.gov/ns/oscal','http://csrc.nist.gov/ns/rmf')) and @name='method'] |
| `oscal-assessment-method-id-cardinality` | has-cardinality | `local-objective` | its target expression is outside the Metapath subset this tool parses: part[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name=('objective','assessment-objective')]/prop[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name='method-id'] |
| `oscal-assessment-objective-cardinality` | has-cardinality | `local-objective` | its target expression is outside the Metapath subset this tool parses: part[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name=('objective','assessment-objective')] |
| `oscal-assessment-objects-cardinality` | has-cardinality | `local-objective` | its target expression is outside the Metapath subset this tool parses: part[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name=('assessment','assessment-method')]/part[has-oscal-namespace('http://csrc.nist.gov/ns/oscal') and @name=('objects','assessment-objects')] |
| `oscal-by-component-export-provided-uuid-index` | index | `control-implementation` | its target expression is outside the Metapath subset this tool parses: implemented-requirement//by-component/export/provided |
| `oscal-index-metadata-party-organizations-uuid` | index | `metadata` | its target expression is outside the Metapath subset this tool parses: party[@type='organization'] |
| `oscal-index-system-implementation-component-uuid-service` | index | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component[@type='service'] |
| `oscal-ssp-by-component-uuid-index` | index | `system-security-plan` | its target expression is outside the Metapath subset this tool parses: control-implementation/implemented-requirement//by-component|doc(system-implementation/leveraged-authorization/link[@rel='system-security-plan']/@href)/system-security-plan/control-implementation/implemented-requirement//by-component |
| `oscal-system-implementation-component-validation-uuid-index` | index | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component[@type='validation'] |
| `oscal-by-component-uuid-index` | index-has-key | `by-component` | its target expression is outside the Metapath subset this tool parses: link[@rel='provided-by'] |
| `oscal-catalog-groups-controls-parts` | index-has-key | `control` | its target expression is outside the Metapath subset this tool parses: link[@rel=('related','required','incorporated-into','moved-to') and starts-with(@href,'#')] |
| `oscal-component-prop-physical-location` | index-has-key | `system-component` | its target expression is outside the Metapath subset this tool parses: prop[@name='physical-location'] |
| `oscal-diagram-index-back-matter-resource-link-rel` | index-has-key | `diagram` | its target expression is outside the Metapath subset this tool parses: link[@rel='diagram' and starts-with(@href,'#')] |
| `oscal-implemented-requirement-index-metadata-party-uuid` | index-has-key | `implemented-requirement` | its target expression is outside the Metapath subset this tool parses: responsible-role[party-uuid]|statement/responsible-role[party-uuid]|.//by-component//responsible-role[party-uuid] |
| `oscal-implemented-requirement-index-metadata-role-id` | index-has-key | `implemented-requirement` | its target expression is outside the Metapath subset this tool parses: responsible-role|statement/responsible-role|.//by-component//responsible-role |
| `oscal-index-metadata-location-uuid` | index-has-key | `defined-component` | its target expression is outside the Metapath subset this tool parses: prop[@name='physical-location'] |
| `oscal-index-system-implementation-component-uuid-service` | index-has-key | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component/link[@rel='uses-service'] |
| `oscal-leveraged-authorization-index-back-matter-resource-ssp` | index-has-key | `leveraged-authorization` | its target expression is outside the Metapath subset this tool parses: link[@rel='system-security-plan' and starts-with(@href,'#')] |
| `oscal-metadata-link-reference-index-back-matter-resource` | index-has-key | `link` | its target expression is outside the Metapath subset this tool parses: .[@rel=('reference') and starts-with(@href,'#')] |
| `oscal-system-implementation-component-depends-on-link-index` | index-has-key | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component/link[@rel='depends-on'] |
| `oscal-system-implementation-component-prop-leveraged-authorization-uuid-index` | index-has-key | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component/prop[@name='leveraged-authorization-uuid'] |
| `oscal-system-implementation-validation-index` | index-has-key | `system-implementation` | its target expression is outside the Metapath subset this tool parses: component/link[@rel='validation' and starts-with(@href,'#')] |
| `oscal-system-information-index-back-matter-resource-pia-link-rel` | index-has-key | `system-information` | its target expression is outside the Metapath subset this tool parses: link[@rel='privacy-impact-assessment' and starts-with(@href,'#')] |
| `oscal-back-matter-resource-prop-published-datatype` | matches | `resource` | the value constraint is applied through Metapath datatype coercion |
| `oscal-check-hash-length-SHA2-3-224` | matches | `hash` | the value constraint is applied through Metapath datatype coercion |
| `oscal-check-hash-length-SHA2-3-256` | matches | `hash` | the value constraint is applied through Metapath datatype coercion |
| `oscal-check-hash-length-SHA2-3-384` | matches | `hash` | the value constraint is applied through Metapath datatype coercion |
| `oscal-check-hash-length-SHA2-3-512` | matches | `hash` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-inherited-uuid-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-inherited-uuid-value-datatype` | matches | `defined-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-prop-ipv4address-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-prop-ipv6address-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-prop-isa-date-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-prop-uri-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-release-date-value-datatype` | matches | `system-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-component-release-date-value-datatype` | matches | `defined-component` | the value constraint is applied through Metapath datatype coercion |
| `oscal-diagram-datatype-uri` | matches | `diagram` | the value constraint is applied through Metapath datatype coercion |
| `oscal-diagram-datatype-uri-reference` | matches | `diagram` | the value constraint is applied through Metapath datatype coercion |
| `oscal-leveraged-authorization-link-rel-ssp-datatype-uri` | matches | `leveraged-authorization` | the value constraint is applied through Metapath datatype coercion |
| `oscal-leveraged-authorization-link-rel-ssp-datatype-uri-reference` | matches | `leveraged-authorization` | the value constraint is applied through Metapath datatype coercion |
| `oscal-metadata-link-reference-href-datatype-uri` | matches | `link` | the value constraint is applied through Metapath datatype coercion |
| `oscal-metadata-link-reference-href-datatype-uri-reference` | matches | `link` | the value constraint is applied through Metapath datatype coercion |
| `oscal-metadata-link-resource-fragment-datatype` | matches | `link` | the value constraint is applied through Metapath datatype coercion |
| `oscal-metadata-location-address-country-regex` | matches | `country` | the value constraint is applied through Metapath datatype coercion |
| `oscal-metadata-telephone-number-regex` | matches | `telephone-number` | the value constraint is applied through Metapath datatype coercion |
| `oscal-risk-priority-datatype` | matches | `risk` | the value constraint is applied through Metapath datatype coercion |
| `oscal-system-information-pia-datatype-uri` | matches | `system-information` | the value constraint is applied through Metapath datatype coercion |
| `oscal-system-information-pia-datatype-uri-reference` | matches | `system-information` | the value constraint is applied through Metapath datatype coercion |
