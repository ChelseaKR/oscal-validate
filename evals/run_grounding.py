"""Citation grounding and walkthrough fidelity on real documents.

    uv run python -m evals.run_grounding [--cassette ...] [--replay] [--docs id ...]

Two suites in one pass over the published NIST documents, because both are
about whether the model stayed inside what the validator and the corpus
gave it.

Grounding (``explain``): for up to ``--per-doc`` findings per document, the
findings chosen to span severities, the explanation's quotes are counted
as verified (found verbatim in the named source) or withheld, the inline
quotations the verifier struck are counted, and the sentences the boundary
guard withheld are counted. An explanation with no verified quote at all is
counted separately: it is an explanation that could not ground itself.

Fidelity (``walkthrough``): one walkthrough per document; the labels the
model used that the validator never produced (struck) and the groups the
narrative never mentioned (appended by the tool) are counted, with the
guard's withheld sentences.

All counts are the verifier's and the guard's, which do not involve a model.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from evals.common import (
    RESULTS,
    ModelClient,
    ModelError,
    client_from_env,
    merge_results,
    not_run,
    provenance,
    write_results,
)
from evals.documents import Document, load_documents
from oscal_validate.ai import explain, walkthrough
from oscal_validate.ai.run import Run, prepare
from oscal_validate.findings import Finding

SEVERITY_ORDER = ("ERROR", "WARNING", "INFO", "UNVERIFIABLE")


def pick_findings(run: Run, limit: int) -> list[Finding]:
    """Up to ``limit`` findings, rotating across severities so each is represented."""
    by_severity: dict[str, list[Finding]] = {s: [] for s in SEVERITY_ORDER}
    for finding in run.findings:
        by_severity[finding.severity.value].append(finding)
    chosen: list[Finding] = []
    while len(chosen) < limit and any(by_severity.values()):
        for severity in SEVERITY_ORDER:
            if by_severity[severity] and len(chosen) < limit:
                chosen.append(by_severity[severity].pop(0))
    return chosen


def score_grounding(document: Document, client: ModelClient, per_doc: int) -> list[dict[str, Any]]:
    run = prepare(document.path, list(document.resolve))
    records: list[dict[str, Any]] = []
    for finding in pick_findings(run, per_doc):
        result = explain.explain_one(run, finding, client)
        record: dict[str, Any] = {
            "document": document.identifier,
            "model": document.model,
            "label": result.label,
            "code": finding.code,
            "severity": finding.severity.value,
            "served_model": result.served_model,
        }
        if result.verified is None:
            record["skipped"] = result.skipped
        else:
            v = result.verified
            inline = sum(1 for w in v.withheld_quotes if "inline" in w.reason)
            record.update(
                {
                    "quotes_verified": len(v.quotes),
                    "quotes_withheld": len(v.withheld_quotes) - inline,
                    "inline_struck": inline,
                    "sentences_withheld": len(v.withheld_sentences),
                    "refused": v.refused,
                    "grounded": len(v.quotes) >= 1,
                    "sources": sorted({q.source for q in v.quotes}),
                }
            )
        records.append(record)
        print(
            f"explain {document.identifier:32} {result.label:5} {finding.code:26} "
            f"verified={record.get('quotes_verified')} withheld={record.get('quotes_withheld')}",
            flush=True,
        )
    return records


def score_walkthrough(document: Document, client: ModelClient) -> dict[str, Any]:
    run = prepare(document.path, list(document.resolve))
    result = walkthrough.walk(run, client)
    record: dict[str, Any] = {
        "document": document.identifier,
        "model": document.model,
        "findings": len(run.findings),
        "groups": len(result.groups),
        "served_model": result.served_model,
    }
    if result.skipped:
        record["skipped"] = result.skipped
    else:
        record.update(
            {
                "groups_covered": result.covered,
                "not_covered": [g.label for g in result.not_covered],
                "invented_labels": result.invented,
                "sentences_withheld": result.withheld_sentences,
                "steps": len(result.steps),
                "refused": result.refused,
                "complete": not result.not_covered,
                "faithful": not result.invented,
            }
        )
    covered = f"{record.get('groups_covered')}/{record['groups']}"
    print(
        f"walk    {document.identifier:32} covered={covered} "
        f"invented={len(record.get('invented_labels', []))}",
        flush=True,
    )
    return record


def summarize(grounding: list[dict[str, Any]], walks: list[dict[str, Any]]) -> dict[str, Any]:
    g = [r for r in grounding if "skipped" not in r]
    w = [r for r in walks if "skipped" not in r]
    return {
        "cases": len(grounding) + len(walks),
        "grounding": {
            "explanations": len(g),
            "skipped": len(grounding) - len(g),
            "quotes_verified": sum(r["quotes_verified"] for r in g),
            "quotes_withheld": sum(r["quotes_withheld"] for r in g),
            "inline_struck": sum(r["inline_struck"] for r in g),
            "sentences_withheld": sum(r["sentences_withheld"] for r in g),
            "grounded": sum(int(r["grounded"]) for r in g),
            "ungrounded": [f"{r['document']}:{r['label']}" for r in g if not r["grounded"]],
            "refused": sum(int(r["refused"]) for r in g),
        },
        "walkthrough": {
            "documents": len(w),
            "skipped": len(walks) - len(w),
            "complete": sum(int(r["complete"]) for r in w),
            "faithful": sum(int(r["faithful"]) for r in w),
            "groups_total": sum(r["groups"] for r in w),
            "groups_covered": sum(r["groups_covered"] for r in w),
            "invented_labels": sum(len(r["invented_labels"]) for r in w),
            "sentences_withheld": sum(r["sentences_withheld"] for r in w),
        },
    }


def _summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    grounding = [r for r in records if "label" in r]
    walks = [r for r in records if "label" not in r]
    return summarize(grounding, walks)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--merge", nargs="+", type=Path, help="merge these shard results")
    parser.add_argument("--cassette", type=Path)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--docs", nargs="*")
    parser.add_argument("--per-doc", type=int, default=4)
    args = parser.parse_args(argv)
    out = args.out or RESULTS / f"grounding-{dt.date.today().isoformat()}.json"
    if args.merge:
        merged = merge_results(
            args.merge,
            out,
            _summarize_records,
            lambda r: f"{r['document']}|{r.get('label', 'walk')}",
        )
        print(json.dumps(merged["summary"], indent=2))
        return 0
    documents, skipped_docs = load_documents()
    if args.docs:
        documents = [d for d in documents if d.identifier in set(args.docs)]
    try:
        client = client_from_env(args.cassette, replay=args.replay)
    except ModelError as exc:
        write_results(out, not_run("grounding", str(exc)))
        print(f"not run: {exc}", file=sys.stderr)
        return 2
    grounding: list[dict[str, Any]] = []
    walks: list[dict[str, Any]] = []
    for document in documents:
        grounding.extend(score_grounding(document, client, args.per_doc))
        walks.append(score_walkthrough(document, client))
    served = next((r.get("served_model") for r in grounding + walks if r.get("served_model")), None)
    payload = {
        "provenance": provenance("grounding", client, served, {"documents_skipped": skipped_docs}),
        "summary": summarize(grounding, walks),
        "cases": grounding + walks,
    }
    write_results(out, payload)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
