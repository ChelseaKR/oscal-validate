"""Repair efficacy on real documents with injected defects, measured by re-validation.

    uv run python -m evals.run_repair [--cassette ...] [--replay] [--docs ...] [--injectors ...]

For each published NIST document and each defect injector, the defect is
injected into a copy, the copy is validated, and the findings that appeared
because of the injection are the targets. ``repair --draft`` is run for each
target (ERROR findings only; the injectors produce ERRORs on a complete
effective data model) and the draft's outcome is what the deterministic
validator found when it re-validated the patched copy:

- ``resolved``: the target finding is gone;
- ``clean``: resolved and no finding was introduced;
- ``introduced``: at least one new finding appeared;
- ``no_draft``: the model proposed no usable patch, or the patch was refused
  (implementation narrative, inapplicable path, disallowed operation).

Every number here is a count of validator findings, never a model's claim.
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
from evals.documents import INJECTORS, Document, load_documents, materialized
from oscal_validate.ai import repair
from oscal_validate.ai.run import prepare
from oscal_validate.findings import Severity


def _targets(
    document: Document, corrupted_path: Path, baseline_keys: set[tuple[str, str, str, str]]
) -> Any:
    run = prepare(corrupted_path, list(document.resolve))
    targets = [
        f
        for f in run.findings
        if f.severity is Severity.ERROR and repair.finding_key(f) not in baseline_keys
    ]
    return run, targets


def score_document(
    document: Document, injectors: list[str], client: ModelClient, per_target_limit: int
) -> list[dict[str, Any]]:
    baseline = prepare(document.path, list(document.resolve))
    baseline_keys = {repair.finding_key(f) for f in baseline.findings}
    records: list[dict[str, Any]] = []
    for name in injectors:
        corrupted = INJECTORS[name](document.payload)
        base: dict[str, Any] = {
            "document": document.identifier,
            "model": document.model,
            "injector": name,
        }
        if corrupted is None:
            records.append({**base, "skipped": "the document has no place for this defect"})
            continue
        with materialized(document, corrupted) as path:
            run, targets = _targets(document, path, baseline_keys)
            if not targets:
                records.append({**base, "skipped": "the injection produced no new ERROR finding"})
                continue
            for target in targets[:per_target_limit]:
                draft = repair.repair_one(run, target, client)
                record = {
                    **base,
                    "target": {
                        "code": target.code,
                        "location": target.location,
                        "prop": target.prop,
                    },
                    "label": draft.label,
                    "served_model": draft.served_model,
                }
                if draft.outcome is None:
                    record.update(
                        {
                            "no_draft": True,
                            "reason": draft.skipped,
                            "resolved": False,
                            "clean": False,
                        }
                    )
                else:
                    o = draft.outcome
                    record.update(
                        {
                            "no_draft": False,
                            "resolved": o.resolved,
                            "clean": o.resolved and not o.introduced,
                            "introduced": [f.code for f in o.introduced],
                            "also_resolved": [f.code for f in o.also_resolved],
                            "changed": len(o.changed),
                            "patch": [op.to_dict() for op in draft.patch],
                            "placeholders": len(draft.placeholders),
                            "before": o.before,
                            "after": o.after,
                        }
                    )
                records.append(record)
                print(
                    f"{document.identifier:32} {name:17} {target.code:26} "
                    f"resolved={record['resolved']} clean={record['clean']}",
                    flush=True,
                )
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [r for r in records if "skipped" not in r]
    by_injector: dict[str, dict[str, int]] = {}
    for r in scored:
        bucket = by_injector.setdefault(
            r["injector"], {"n": 0, "resolved": 0, "clean": 0, "introduced": 0, "no_draft": 0}
        )
        bucket["n"] += 1
        bucket["resolved"] += int(r["resolved"])
        bucket["clean"] += int(r["clean"])
        bucket["introduced"] += int(bool(r.get("introduced")))
        bucket["no_draft"] += int(r["no_draft"])
    return {
        "cases": len(records),
        "skipped": len(records) - len(scored),
        "targets": len(scored),
        "resolved": sum(int(r["resolved"]) for r in scored),
        "clean": sum(int(r["clean"]) for r in scored),
        "introduced_any": sum(int(bool(r.get("introduced"))) for r in scored),
        "no_draft": sum(int(r["no_draft"]) for r in scored),
        "by_injector": by_injector,
        "documents": sorted({r["document"] for r in records}),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--merge", nargs="+", type=Path, help="merge these shard results")
    parser.add_argument("--cassette", type=Path)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--docs", nargs="*")
    parser.add_argument("--injectors", nargs="*", default=list(INJECTORS))
    parser.add_argument("--per-target-limit", type=int, default=2)
    args = parser.parse_args(argv)
    out = args.out or RESULTS / f"repair-{dt.date.today().isoformat()}.json"
    if args.merge:
        merged = merge_results(
            args.merge,
            out,
            summarize,
            lambda r: f"{r['document']}|{r['injector']}|{r.get('label', '')}",
        )
        print(json.dumps(merged["summary"], indent=2))
        return 0
    documents, skipped_docs = load_documents()
    if args.docs:
        documents = [d for d in documents if d.identifier in set(args.docs)]
    try:
        client = client_from_env(args.cassette, replay=args.replay)
    except ModelError as exc:
        write_results(out, not_run("repair", str(exc)))
        print(f"not run: {exc}", file=sys.stderr)
        return 2
    records: list[dict[str, Any]] = []
    for document in documents:
        records.extend(score_document(document, args.injectors, client, args.per_target_limit))
    served = next((r.get("served_model") for r in records if r.get("served_model")), None)
    payload = {
        "provenance": provenance(
            "repair",
            client,
            served,
            {"documents_skipped": skipped_docs, "injectors": args.injectors},
        ),
        "summary": summarize(records),
        "cases": records,
    }
    write_results(out, payload)
    print(json.dumps(payload["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
