# Data card: the published OSCAL documents behind `docs/findings/`

The corpus the survey runs are about. It is fetched by a development harness,
never by the installed package, and none of it is committed to this repository.

| | |
|---|---|
| Sources | **2026-08-14 and 2026-08-15 runs**, listed in [`../../tools/survey-urls.txt`](../../tools/survey-urls.txt): `usnistgov/oscal-content`; `OSCAL-Foundation/fedramp-automation` and `OSCAL-Foundation/fedramp-resources`; `awslabs/oscal-content-for-aws-services`; `EasyDynamics/oscal-viewer`; `ComplianceAsCode/oscal-content`; `IBM/oscal-exchange-protocol`. **2026-08-19 run**, listed in [`../../tools/survey-urls-2026-08-19.txt`](../../tools/survey-urls-2026-08-19.txt): `BSI-Bund/Stand-der-Technik-Bibliothek`; `AustralianCyberSecurityCentre/ism-oscal`; `usnistgov/blossom-oscal`; `GSA-TTS/cg-egress-proxy`; `rsherwood-gsa/OSCAL-CSP`; `SunStone-Secure-LLC/OSCAL-Plugfest-2025`; `oscal-compass/oscal-content`, `oscal-compass/e2e-demo-ssp`, `oscal-compass/compliance-to-policy-go` and `oscal-compass/compliance-trestle`; `nickmahl/oscal-trestle-viewer`; `sam-aydlette/samaydlette.com`; `RedHatProductSecurity/trestle-demo` and `RedHatProductSecurity/oscal-profiles`; `mitre/hdf-libs`; `NTT-Data-Deutschland-SE/Grundschutz-Plus-Plus-Tools`; `NTTDATA-DACH/BSI-GS-Benutzerdefinierte-Edition23-OSCAL`; `CivicActions/oscal-component-definitions`; `GovReady/components-stig`; `sbomify/OSCAL`; `ContainerSolutions/oscal-neo4j`; `l3montree-dev/devguard`; `dfetch-org/dfetch`; `pqctoday-org/pqctoday-hub`; `oasis-open/openc2-jadn-software` |
| What is taken | 95 survey targets across three runs — 52 from 2026-08-14/15 (26.1 MB) and 43 from 2026-08-19 (4.9 MB) — plus the supporting documents those targets import: 15 for the second run (31.3 MB) and 8 for the third (13.3 MB). The two target lists are disjoint, which `tests/test_findings_evidence.py` enforces, so the 95 is a sum and not a double-count |
| How | [`../../tools/fetch.py`](../../tools/fetch.py): `robots.txt` first and obeyed with no override flag, an unreachable `robots.txt` treated as a complete disallow per RFC 9309 2.3.1.4, an identifying User-Agent naming the tool, at most five redirects with robots re-checked at each hop, a byte cap, a timeout, and a two-second minimum per host that a site's `Crawl-delay` can lengthen |
| Retrieved | 2026-08-14, 2026-08-15, and 2026-08-19. Cached on disk under `.survey-cache/`, which is git-ignored, so a re-run needs no network |
| Tier | L1, public and non-sensitive. Published specification content, baselines, templates, agency control libraries, interoperability-event samples, and vendor samples. No real system's security posture is in the sample; the FedRAMP SSP example is an example, and the BLOSSOM and Plugfest system security plans are published as worked examples by the organisations that wrote them |
| Licence | NIST content is US-government public domain with a CC0 1.0 waiver. BSI publishes under CC-BY-SA-4.0. Apache-2.0 for the OSCAL Compass repositories, Red Hat's `trestle-demo`, `NTT-Data-Deutschland-SE`, `sbomify` and OASIS; MIT for CivicActions, `dfetch-org` and `sam-aydlette`; GPL-3.0 for `pqctoday-org`; a repository-specific licence for `GSA-TTS`, `mitre/hdf-libs`, `NTTDATA-DACH` and `l3montree-dev`. **Nine state no licence at all**: `AustralianCyberSecurityCentre/ism-oscal`, `usnistgov/blossom-oscal`, `rsherwood-gsa/OSCAL-CSP`, both SunStone repositories, `nickmahl/oscal-trestle-viewer`, `GovReady/components-stig`, `ContainerSolutions/oscal-neo4j`, and the two FedRAMP repositories. That is precisely why only metadata and finding codes are recorded from any of them and no document content is committed here; a reader wanting to redistribute the documents themselves must check each repository rather than this row |
| What is committed | The finding codes, their counts, one JSON Pointer per code, the HTTP outcome, and the byte size, in `docs/findings/*.json`. **No value read from any document.** `tests/test_findings_evidence.py` fails if a record grows a key outside that set |
| Refresh trigger | A new OSCAL release, or a decision to re-measure. All three runs are dated in their file names and none is presented as current |
| Retention | Indefinite for the committed evidence, which is the finding. The fetched bytes are a local cache and are not retained anywhere in this repository |

## Known limitations

- **The five runs committed here are dated at the file level; runs made from
  now on are dated per record.** A record's `fetch` block carries the requested
  URL, the final URL after redirects, the HTTP status, what `robots.txt` said,
  and — since 2026-09-05 — `fetched_at`, the UTC moment the bytes arrived.
  Every run in this repository predates that field, and **none has been
  backfilled**: a date invented after the fact would be worse than the file
  name, which at least records when the run was written down. For these five
  files the "Retrieved" row above and the file names remain the lineage. A
  record whose bytes came from the cache and whose provenance was not carried
  forward has no `fetch` block, and so no date, rather than being stamped with
  the moment it was read.
- **A document that is both a target and a supporting document is fetched once.**
  Its provenance is recorded in the `supporting` block and its target record
  reads `read from cache`. That is accurate rather than missing, but it means
  the fetch metadata for those documents is one indirection away. Narrowed on
  2026-08-19: `survey.py --provenance` carries an earlier run's `fetch` record
  into a later run's own records, so a document retrieved by the 2026-08-14 run
  and reused by the 2026-08-19 run carries its retrieval evidence in both. It
  does not close the case where a document is a target and a supporting document
  *within one run*, which is 5 of the 43 records in the third run.
- **The sample is purposive, not random.** No population estimate follows from
  it. All three write-ups say so at length.
- **The third run's publishers were found by search.** A publisher who ships
  OSCAL only behind a login, or only in XML or YAML, could not be found this way,
  so the absence of a sector or a country from the table is not evidence that it
  publishes nothing.
- **One model was represented but barely read, until 2026-08-27.** All seven
  `mapping-collection` documents reported `SUBTREE_NOT_READ` at
  `/mapping-collection/mappings` in the runs recorded here, so their
  contribution to those runs is metadata conformance and almost nothing else.
  ADR-0007 resolved the shape that blocked the walk; the same seven documents
  read today report no `SUBTREE_NOT_READ` and 31 ERROR findings. The recorded
  runs are not re-scored, because they are the record of what those runs found.
- **Publishers change.** `GSA/fedramp-automation`, where the FedRAMP baselines
  and templates were originally published, was archived in July 2025 and has
  since been removed from GitHub, and `automate.fedramp.gov` no longer resolves
  in DNS. One survey target imports a document by an absolute URL into that
  deleted repository. The reachable fork is used instead, and the substitution
  is disclosed in the write-up rather than papered over.
