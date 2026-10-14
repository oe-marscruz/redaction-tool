"""Deterministic evaluation of detector recall/precision on the synthetic corpus.

Metrics include:
1. Category-Correct 1-to-1 Matching (Primary Strict Metric)
2. Exact-Span 1-to-1 Matching
3. Character-Level Coverage
4. Duplicate-Overlap Accounting
5. Legacy Overlap Matching (Lenient Overlap)
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from tests.eval_corpus import GoldEntity, build_corpus  # noqa: E402


# An opt-in detection supplement may add recall, but it must never meaningfully
# degrade the detector it supplements. These bound the tolerated regression.
AB_MAX_RECALL_DROP = 0.0
AB_MAX_PRECISION_DROP = 0.02


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
    legacy_overlap: Counts = field(default_factory=Counts)
    by_category_legacy: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    by_bucket_legacy: dict[str, Counts] = field(default_factory=lambda: defaultdict(Counts))
    exact_span: Counts = field(default_factory=Counts)
    char_tp: int = 0
    char_fp: int = 0
    char_fn: int = 0
    duplicate_overlaps: int = 0
    false_negatives: list[dict] = field(default_factory=list)
    false_positives: list[dict] = field(default_factory=list)
    n_docs: int = 0
    n_gold: int = 0
    n_pred: int = 0

    def as_dict(self) -> dict:
        char_denom_p = self.char_tp + self.char_fp
        char_denom_r = self.char_tp + self.char_fn
        char_p = self.char_tp / char_denom_p if char_denom_p else 1.0
        char_r = self.char_tp / char_denom_r if char_denom_r else 1.0
        char_f1 = 2 * char_p * char_r / (char_p + char_r) if (char_p + char_r) else 0.0

        return {
            "n_docs": self.n_docs,
            "n_gold": self.n_gold,
            "n_pred": self.n_pred,
            "overall": self.overall.as_dict(),
            "legacy_overlap": self.legacy_overlap.as_dict(),
            "exact_span": self.exact_span.as_dict(),
            "character_coverage": {
                "tp_chars": self.char_tp,
                "fp_chars": self.char_fp,
                "fn_chars": self.char_fn,
                "precision": round(char_p, 4),
                "recall": round(char_r, 4),
                "f1": round(char_f1, 4),
            },
            "duplicate_overlap_count": self.duplicate_overlaps,
            "by_category": {k: v.as_dict() for k, v in sorted(self.by_category.items())},
            "by_bucket": {k: v.as_dict() for k, v in sorted(self.by_bucket.items())},
            "by_category_legacy": {k: v.as_dict() for k, v in sorted(self.by_category_legacy.items())},
            "by_bucket_legacy": {k: v.as_dict() for k, v in sorted(self.by_bucket_legacy.items())},
            "false_negative_count": len(self.false_negatives),
            "false_positive_count": len(self.false_positives),
            "false_negatives_sample": self.false_negatives[:40],
            "false_positives_sample": self.false_positives[:40],
            "disclaimer": "Synthetic evaluation benchmark results. 100% corpus recall on synthetic fixtures does not claim or guarantee perfect production recall or HIPAA/FERPA certification.",
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

        # ── 1. Character-level coverage ────────────────────────────────────
        gold_char_set: set[int] = set()
        for g in doc.entities:
            gold_char_set.update(range(g.start, g.end))

        pred_char_set: set[int] = set()
        for p in preds:
            pred_char_set.update(range(p.start, p.end))

        char_tp = len(gold_char_set & pred_char_set)
        char_fp = len(pred_char_set - gold_char_set)
        char_fn = len(gold_char_set - pred_char_set)

        result.char_tp += char_tp
        result.char_fp += char_fp
        result.char_fn += char_fn

        # ── 2. Legacy lenient overlap matching ──────────────────────────────
        legacy_matched_pred: set[int] = set()
        for gi, g in enumerate(doc.entities):
            hit = False
            for pi, p in enumerate(preds):
                if _overlaps(p.start, p.end, g.start, g.end) or _covers_value(p.text, g.value):
                    hit = True
                    legacy_matched_pred.add(pi)
                    break
            if hit:
                result.legacy_overlap.tp += 1
                result.by_category_legacy[g.category].tp += 1
                result.by_bucket_legacy[_bucket(g.category, g.tags + doc.tags)].tp += 1
            else:
                result.legacy_overlap.fn += 1
                result.by_category_legacy[g.category].fn += 1
                result.by_bucket_legacy[_bucket(g.category, g.tags + doc.tags)].fn += 1

        for pi, p in enumerate(preds):
            if pi in legacy_matched_pred:
                continue
            fp = True
            for g in doc.entities:
                if _overlaps(p.start, p.end, g.start, g.end) or _covers_value(p.text, g.value):
                    fp = False
                    break
            if fp:
                result.legacy_overlap.fp += 1
                result.by_category_legacy[p.category].fp += 1
                result.by_bucket_legacy[_bucket(p.category, doc.tags)].fp += 1

        # ── 3. Exact-span 1-to-1 matching ──────────────────────────────────
        exact_candidates = []
        for gi, g in enumerate(doc.entities):
            for pi, p in enumerate(preds):
                if p.category == g.category and p.start == g.start and p.end == g.end:
                    exact_candidates.append((gi, pi))

        assigned_exact_g: set[int] = set()
        assigned_exact_p: set[int] = set()
        for gi, pi in exact_candidates:
            if gi not in assigned_exact_g and pi not in assigned_exact_p:
                assigned_exact_g.add(gi)
                assigned_exact_p.add(pi)
                result.exact_span.tp += 1

        result.exact_span.fn += (len(doc.entities) - len(assigned_exact_g))
        result.exact_span.fp += (len(preds) - len(assigned_exact_p))

        # ── 4. Strict category-correct 1-to-1 matching ──────────────────────
        candidate_matches = []
        for gi, g in enumerate(doc.entities):
            for pi, p in enumerate(preds):
                if p.category != g.category:
                    continue
                overlaps = _overlaps(p.start, p.end, g.start, g.end)
                covers = _covers_value(p.text, g.value)
                if overlaps or covers:
                    score = 0.0
                    if p.start == g.start and p.end == g.end:
                        score = 3.0
                    elif _norm(p.text) == _norm(g.value):
                        score = 2.0
                    else:
                        score = 1.0
                    candidate_matches.append((score, gi, pi))

        candidate_matches.sort(key=lambda x: x[0], reverse=True)

        assigned_g: set[int] = set()
        assigned_p: set[int] = set()

        for score, gi, pi in candidate_matches:
            if gi not in assigned_g and pi not in assigned_p:
                assigned_g.add(gi)
                assigned_p.add(pi)
                g = doc.entities[gi]
                result.overall.tp += 1
                result.by_category[g.category].tp += 1
                result.by_bucket[_bucket(g.category, g.tags + doc.tags)].tp += 1

        for gi, g in enumerate(doc.entities):
            if gi not in assigned_g:
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
            if pi not in assigned_p:
                result.overall.fp += 1
                result.by_category[p.category].fp += 1
                result.by_bucket[_bucket(p.category, doc.tags)].fp += 1
                result.false_positives.append({
                    "doc_id": doc.doc_id,
                    "value": p.text,
                    "category": p.category,
                    "text": doc.text[:160],
                })

                # Check if this unmatched prediction overlaps a gold entity (duplicate/redundant)
                if any(_overlaps(p.start, p.end, g.start, g.end) for g in doc.entities):
                    result.duplicate_overlaps += 1

    return result


def main() -> int:
    from redaction_tool.detector import detect, presidio_is_available

    print("Running baseline synthetic evaluation (use_presidio=False)...")
    t0 = time.perf_counter()
    res = evaluate(lambda text: detect(text, use_presidio=False))
    t_base = time.perf_counter() - t0

    payload = res.as_dict()
    payload["time_seconds"] = round(t_base, 3)

    if presidio_is_available():
        print("Running Presidio synthetic evaluation (use_presidio=True)...")
        t1 = time.perf_counter()
        res_presidio = evaluate(lambda text: detect(text, use_presidio=True))
        t_presidio = time.perf_counter() - t1

        payload["ab_comparison"] = {
            "status": "PASS",
            "baseline": {
                "overall": res.overall.as_dict(),
                "time_seconds": round(t_base, 3),
                "fp_count": len(res.false_positives),
                "fn_count": len(res.false_negatives),
            },
            "presidio": {
                "overall": res_presidio.overall.as_dict(),
                "time_seconds": round(t_presidio, 3),
                "fp_count": len(res_presidio.false_positives),
                "fn_count": len(res_presidio.false_negatives),
            },
            "observations": {
                "latency_delta_seconds": round(t_presidio - t_base, 3),
                "recall_change": round(res_presidio.overall.recall() - res.overall.recall(), 4),
                "precision_change": round(res_presidio.overall.precision() - res.overall.precision(), 4),
            },
        }
        # The opt-in Presidio supplement must not degrade the detector it
        # supplements. Gate the comparison instead of reporting PASS
        # unconditionally, so a regression fails here rather than at review.
        ab = payload["ab_comparison"]
        regressions = []
        recall_drop = res.overall.recall() - res_presidio.overall.recall()
        precision_drop = res.overall.precision() - res_presidio.overall.precision()
        if recall_drop > AB_MAX_RECALL_DROP:
            regressions.append(
                f"recall dropped by {recall_drop:.4f} (limit {AB_MAX_RECALL_DROP})")
        if precision_drop > AB_MAX_PRECISION_DROP:
            regressions.append(
                f"precision dropped by {precision_drop:.4f} (limit {AB_MAX_PRECISION_DROP})")
        if regressions:
            ab["status"] = "FAIL"
            ab["regressions"] = regressions
        else:
            ab["limits"] = {
                "max_recall_drop": AB_MAX_RECALL_DROP,
                "max_precision_drop": AB_MAX_PRECISION_DROP,
            }
    else:
        payload["ab_comparison"] = {
            "status": "BLOCKED",
            "reason": "Presidio or pinned en_core_web_sm model unavailable in execution environment",
        }

    out = Path(__file__).parent / "eval_last.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    o = payload["overall"]
    leg = payload["legacy_overlap"]
    exact = payload["exact_span"]
    cc = payload["character_coverage"]

    print(f"docs={payload['n_docs']} gold={payload['n_gold']} pred={payload['n_pred']}")
    print(f"Strict 1:1 Cat-Correct P={o['precision']:.4f} R={o['recall']:.4f} F1={o['f1']:.4f} FN={o['fn']} FP={o['fp']}")
    print(f"Legacy Overlap        P={leg['precision']:.4f} R={leg['recall']:.4f} F1={leg['f1']:.4f}")
    print(f"Exact Span            P={exact['precision']:.4f} R={exact['recall']:.4f} F1={exact['f1']:.4f}")
    print(f"Char-level Coverage   P={cc['precision']:.4f} R={cc['recall']:.4f} F1={cc['f1']:.4f}")
    print(f"Duplicate overlaps:   {payload['duplicate_overlap_count']}")
    ab = payload["ab_comparison"]
    print(f"A/B Comparison:       {ab['status']}")
    if ab["status"] == "FAIL":
        for reason in ab.get("regressions", []):
            print(f"  REGRESSION: {reason}")
    print("by_bucket (strict 1:1):")
    for k, v in payload["by_bucket"].items():
        print(f"  {k:12s} P={v['precision']:.4f} R={v['recall']:.4f} FN={v['fn']} FP={v['fp']}")
    print("by_category (strict 1:1):")
    for k, v in payload["by_category"].items():
        print(f"  {k:16s} P={v['precision']:.4f} R={v['recall']:.4f} FN={v['fn']} FP={v['fp']}")
    print(f"wrote {out}")
    # A blocked comparison (Presidio not installed) is not a regression; an
    # explicit FAIL is, and must not pass silently in CI.
    return 1 if ab["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
