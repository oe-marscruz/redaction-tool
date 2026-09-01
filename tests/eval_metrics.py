"""Deterministic evaluation of detector recall/precision on the synthetic corpus.

Matching is redaction-oriented: a gold entity is recalled if any predicted
span overlaps the gold span or the predicted text covers the gold value.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from tests.eval_corpus import GoldEntity, build_corpus  # noqa: E402


@dataclass
class Counts:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 1.0

    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 1.0

    def f1(self) -> float:
        p, r = self.precision(), self.recall()
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision(), 4),
            "recall": round(self.recall(), 4),
            "f1": round(self.f1(), 4),
        }


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


def _overlaps(a0: int, a1: int, b0: int, b1: int) -> bool:
    return a0 < b1 and a1 > b0


def _covers_value(pred_text: str, gold_value: str) -> bool:
    p = _norm(pred_text)
    g = _norm(gold_value)
    if not p or not g:
        return False
    if p == g:
        return True
    if g in p or p in g:
        return len(min(p, g, key=len)) >= 3
    # OCR-ish: ignore non-alnum
    pa = "".join(ch for ch in p if ch.isalnum())
    ga = "".join(ch for ch in g if ch.isalnum())
    if pa and ga and (pa == ga or ga in pa or pa in ga) and len(min(pa, ga, key=len)) >= 4:
        return True
    return False


@dataclass
class EvalResult:
    overall: Counts = field(default_factory=Counts)
    by_category: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    by_bucket: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    false_negatives: list[dict] = field(default_factory=list)
    false_positives: list[dict] = field(default_factory=list)
    n_docs: int = 0
    n_gold: int = 0
    n_pred: int = 0

    def as_dict(self) -> dict:
        return {
            "n_docs": self.n_docs,
            "n_gold": self.n_gold,
            "n_pred": self.n_pred,
            "overall": self.overall.as_dict(),
            "by_category": {k: v.as_dict() for k, v in sorted(self.by_category.items())},
            "by_bucket": {k: v.as_dict() for k, v in sorted(self.by_bucket.items())},
            "false_negative_count": len(self.false_negatives),
            "false_positive_count": len(self.false_positives),
            "false_negatives_sample": self.false_negatives[:40],
            "false_positives_sample": self.false_positives[:40],
        }


_NAME_CATS = {"names"}
_DATE_CATS = {"dates"}
_STRUCT_CATS = {
    "ssn", "emails", "phones", "fax", "mrn", "health_plan", "accounts",
    "licenses", "vehicles", "devices", "urls", "ips", "unique_ids",
    "biometric", "student_records", "financial",
}
_ADDR_CATS = {"addresses"}


def _bucket(cat: str, tags: list[str]) -> str:
    if "ocr" in tags or "ocr_sub" in tags or "hyphen_wrap" in tags or "line_break" in tags:
        return "ocr"
    if cat in _NAME_CATS:
        return "names"
    if cat in _DATE_CATS:
        return "dates"
    if cat in _ADDR_CATS:
        return "addresses"
    if cat in _STRUCT_CATS:
        return "structured"
    return "other"


def evaluate(detect_fn, docs=None) -> EvalResult:
    docs = docs or build_corpus()
    result = EvalResult(n_docs=len(docs))
    for doc in docs:
        preds = detect_fn(doc.text)
        result.n_pred += len(preds)
        result.n_gold += len(doc.entities)
        matched_pred: set[int] = set()
        matched_gold: set[int] = set()
        for gi, g in enumerate(doc.entities):
            hit = False
            for pi, p in enumerate(preds):
                if _overlaps(p.start, p.end, g.start, g.end) or _covers_value(p.text, g.value):
                    hit = True
                    matched_pred.add(pi)
                    break
            if hit:
                matched_gold.add(gi)
                result.overall.tp += 1
                result.by_category[g.category].tp += 1
                result.by_bucket[_bucket(g.category, g.tags + doc.tags)].tp += 1
            else:
                result.overall.fn += 1
                result.by_category[g.category].fn += 1
                result.by_bucket[_bucket(g.category, g.tags + doc.tags)].fn += 1
                result.false_negatives.append({
                    "doc_id": doc.doc_id,
                    "value": g.value,
                    "category": g.category,
                    "tags": g.tags,
                    "text": doc.text[:160],
                })
        for pi, p in enumerate(preds):
            if pi in matched_pred:
                continue
            # Unmatched prediction: FP unless it overlaps some gold we already counted
            fp = True
            for g in doc.entities:
                if _overlaps(p.start, p.end, g.start, g.end) or _covers_value(p.text, g.value):
                    fp = False
                    break
            if fp:
                result.overall.fp += 1
                result.by_category[p.category].fp += 1
                result.by_bucket[_bucket(p.category, doc.tags)].fp += 1
                result.false_positives.append({
                    "doc_id": doc.doc_id,
                    "value": p.text,
                    "category": p.category,
                    "text": doc.text[:160],
                })
    return result


def main() -> int:
    from redaction_tool.detector import detect

    result = evaluate(detect)
    payload = result.as_dict()
    out = Path(__file__).parent / "eval_last.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    o = payload["overall"]
    print(f"docs={payload['n_docs']} gold={payload['n_gold']} pred={payload['n_pred']}")
    print(f"overall P={o['precision']:.4f} R={o['recall']:.4f} F1={o['f1']:.4f} "
          f"FN={o['fn']} FP={o['fp']}")
    print("by_bucket:")
    for k, v in payload["by_bucket"].items():
        print(f"  {k:12s} P={v['precision']:.4f} R={v['recall']:.4f} FN={v['fn']} FP={v['fp']}")
    print("by_category:")
    for k, v in payload["by_category"].items():
        print(f"  {k:16s} P={v['precision']:.4f} R={v['recall']:.4f} FN={v['fn']} FP={v['fp']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
