# Data card: the NIST documentation corpus

The only text the model-backed commands of ADR-0005 may quote. A model
explains a rule by quoting this text, and every quote is checked verbatim
against it before display.

| | |
|---|---|
| Source | NIST, twenty pages under `https://pages.nist.gov/OSCAL/`, `https://pages.nist.gov/OSCAL-Reference/models/v1.2.3/`, and `https://pages.nist.gov/metaschema/`: the identifier-use, URI-use, validation, and layer-overview concept pages; one concept page per model; the Metaschema constraint and datatype specifications; and the generated JSON reference for each of the seven models at v1.2.3. The list is `tools/corpus-urls.txt` |
| What is taken | The page text, extracted by the standard library's HTML parser in the fixed way `tools/corpus_fetch.py` documents (headings marked, block boundaries kept, scripts, navigation, and footers dropped). The raw HTML is not kept; its SHA-256 is |
| Retrieved | 2026-08-21, through `tools/fetch.py` (robots.txt first and obeyed, identifying User-Agent, byte cap, per-host rate limit) |
| Where it lives | `src/oscal_validate/ai/corpus/`, shipped as package data, 4.2 MB of text. The vendored schema and metaschema under `vendor/` are sources too, under ids of the form `vendor:<file>` |
| Tier | L1, public and non-sensitive. Specification prose; nothing about any real system |
| Licence | Works of the US National Institute of Standards and Technology; public domain in the United States, CC0 1.0 elsewhere, as `usnistgov/OSCAL` states. Compatible with this repository's Apache-2.0 |
| Integrity | `MANIFEST.json` records, per page, the URL, final URL, title, retrieval date, SHA-256 of the raw bytes as served, and SHA-256 and size of the extracted text. `tests/test_ai_sources.py` recomputes the text hashes on every run and fails on a file without a row or a row without a file |
| Refresh trigger | A new OSCAL release (the reference pages are per-release), or a change to a concept page that a rule in `rules.py` quotes. `tests/test_ai_sources.py` asserts the three prose rules `rules.py` already quotes verify against the corpus, so a re-fetch that changed that wording would fail the build and be noticed |
| Staleness signal | Every quote printed carries the source's retrieval date. There is no runtime alarm on the corpus's age |
| Retention | Indefinite; the corpus is part of the product. Removed within 30 days if the publisher ever revokes or relicenses |

## Known limitations

- **The extraction is lossy by design.** Tables become ` | `-separated
  lines and nested reference entries become nested headings. A quote is
  verified against the extracted text after whitespace is collapsed and
  typographic quotes are straightened; a sentence that NIST's HTML splits
  across elements may not verify as one quote.
- **One reference page is missing.** NIST publishes no JSON reference for
  the mapping-collection model at v1.2.3 (the URL returns 404), so
  findings on that model have no reference-page evidence, which is also
  the model whose content the validator does not read (issue #7).
- **The corpus is what the model is shown, not what it knows.** A model
  can still write from memory; the verifier withholds what it cannot find
  here, and the count of withheld quotes is printed every time.
