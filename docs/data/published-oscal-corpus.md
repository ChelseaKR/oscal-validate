# Data card: the published OSCAL documents behind `docs/findings/`

The corpus the survey runs are about. It is fetched by a development harness,
never by the installed package, and none of it is committed to this repository.

| | |
|---|---|
| Sources | `usnistgov/oscal-content`; `OSCAL-Foundation/fedramp-automation` and `OSCAL-Foundation/fedramp-resources`; `awslabs/oscal-content-for-aws-services`; `EasyDynamics/oscal-viewer`; `ComplianceAsCode/oscal-content`; `IBM/oscal-exchange-protocol`. Every URL is listed in [`../../tools/survey-urls.txt`](../../tools/survey-urls.txt) |
| What is taken | 52 survey targets and, since 2026-08-15, 15 supporting documents named by those targets' imports. 26.1 MB and 31.3 MB respectively |
| How | [`../../tools/fetch.py`](../../tools/fetch.py): `robots.txt` first and obeyed with no override flag, an unreachable `robots.txt` treated as a complete disallow per RFC 9309 2.3.1.4, an identifying User-Agent naming the tool, at most five redirects with robots re-checked at each hop, a byte cap, a timeout, and a two-second minimum per host that a site's `Crawl-delay` can lengthen |
| Retrieved | 2026-08-14 and 2026-08-15. Cached on disk under `.survey-cache/`, which is git-ignored, so a re-run needs no network |
| Tier | L1, public and non-sensitive. Published specification content, baselines, templates, and vendor samples. No real system's security posture is in the sample; the FedRAMP SSP example is an example |
| Licence | NIST content is US-government public domain with a CC0 1.0 waiver. The two FedRAMP repositories state no licence, which is why only metadata and findings are recorded from them. Third-party repositories carry their own licences and are likewise recorded only as metadata |
| What is committed | The finding codes, their counts, one JSON Pointer per code, the HTTP outcome, and the byte size, in `docs/findings/*.json`. **No value read from any document.** `tests/test_findings_evidence.py` fails if a record grows a key outside that set |
| Refresh trigger | A new OSCAL release, or a decision to re-measure. Both runs are dated in their file names and neither is presented as current |
| Retention | Indefinite for the committed evidence, which is the finding. The fetched bytes are a local cache and are not retained anywhere in this repository |

## Known limitations

- **Lineage is dated at the file level, not the record level.** A record carries
  the requested URL, the final URL after redirects, the HTTP status, and what
  `robots.txt` said, but no fetch timestamp; the date lives in the file name.
  That is short of a per-record source-and-timestamp guarantee and is listed as
  an open action in [`../ROADMAP.md`](../ROADMAP.md).
- **A document that is both a target and a supporting document is fetched once.**
  Its provenance is recorded in the `supporting` block and its target record
  reads `read from cache`. That is accurate rather than missing, but it means
  the fetch metadata for those documents is one indirection away.
- **The sample is purposive, not random.** No population estimate follows from
  it. Both write-ups say so at length.
- **Publishers change.** `GSA/fedramp-automation`, where the FedRAMP baselines
  and templates were originally published, was archived in July 2025 and has
  since been removed from GitHub, and `automate.fedramp.gov` no longer resolves
  in DNS. One survey target imports a document by an absolute URL into that
  deleted repository. The reachable fork is used instead, and the substitution
  is disclosed in the write-up rather than papered over.
