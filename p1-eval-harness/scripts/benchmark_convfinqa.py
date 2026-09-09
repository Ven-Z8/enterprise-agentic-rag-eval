"""ConvFinQA benchmark adapter — conversational multi-turn financial QA.

ConvFinQA (EMNLP 2022, Chen et al.): 421 dev conversations / 1,490 turns of
multi-turn financial questions with chained numeric reasoning over annual-
report tables and text. The public test answers are leaderboard-private, so
this adapter measures on the dev split (the standard practice for this
dataset).

What makes this different from the other benchmarks: it exercises the
CONVERSATIONAL pipeline. Each turn is an elliptical follow-up ("what was it
in 2005?", "so what was the percentage change?") — the converse rewriter
must resolve it against the preceding turns into a self-contained question,
then the engine grounds, verifies, and computes the answer. Every turn's
context (the conversation's table + surrounding text) is handed to the
pipeline as evidence; retrieval is isolated out because these annual reports
are out-of-corpus.

Scoring is deterministic (no judge): turn answers are numeric (`exe_ans`,
with percentages stored as fractions). Our answer's numeric claims are
compared at 1% relative tolerance; direction conventions are
magnitude-based ("decreased by $4.0" matches -4.0). Turns whose question
asks for a percentage are scored in percent mode (exe_ans * 100).

Usage:
  uv run python scripts/benchmark_convfinqa.py --limit 5      # smoke
  uv run python scripts/benchmark_convfinqa.py                # full dev split
  uv run python scripts/benchmark_convfinqa.py --dry-run      # offline plumbing check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

P1 = Path(__file__).resolve().parent.parent
P3 = P1.parent / "p3-rag-filings"
sys.path.insert(0, str(P1 / "src"))
sys.path.insert(0, str(P3 / "src"))

from ragfilings.config import load as load_cfg  # noqa: E402
from ragfilings.domains import get_pack  # noqa: E402
from ragfilings.pipeline.converse import rewrite_followup  # noqa: E402
from ragfilings.pipeline.engine import answer  # noqa: E402

CFQ_DIR = P1 / "data" / "convfinqa"
DEV_PATH = CFQ_DIR / "data" / "dev.json"

REL_TOL = 0.01
_PERCENT_Q_RE = re.compile(r"\bpercent(age)?\b|\brate\b|%\s", re.IGNORECASE)


def load_conversations(limit: int | None = None) -> list[dict]:
    convs = json.loads(DEV_PATH.read_text(encoding="utf-8"))
    return convs[:limit] if limit else convs


def render_table(table: list[list[str]]) -> str:
    lines = []
    for row in table:
        cells = [str(c).strip() for c in row]
        if any(cells):
            lines.append(" | ".join(cells))
    return "\n".join(lines)


def context_hits(conv: dict) -> list[dict]:
    """Pseudo-retrieval hits: the conversation's table + surrounding text."""
    hits: list[dict] = []
    name = conv.get("filename") or conv.get("id", "conv")

    def add(text: str, kind: str, i: int) -> None:
        if not text.strip():
            return
        hits.append(
            {
                "chunk": {
                    "id": f"{name}:{kind}:{i}",
                    "text": text,
                    "section": kind,
                    "ticker": None,
                    "company": name,
                    "form": "annual report",
                },
                "score": 0.9,
                "dense_sim": 0.9,
            }
        )

    add(render_table(conv.get("table") or []), "table", 0)
    for i, p in enumerate(conv.get("pre_text") or []):
        add(p, "pre", i)
    for i, p in enumerate(conv.get("post_text") or []):
        add(p, "post", i)
    return hits


def numeric_claims(text: str) -> tuple[list[float], list[float]]:
    """(plain numbers, percent values) claimed by an answer string."""
    plain: list[float] = []
    pcts: list[float] = []
    for m in re.finditer(r"-?\$?\s?([\d,]+(?:\.\d+)?)\s?(%|million|billion|thousand)?", text):
        num = m.group(1)
        if not re.search(r"\d", num):
            continue
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        if m.group(0).strip().startswith("-"):
            v = -v
        unit = m.group(2)
        if unit == "%":
            pcts.append(v)
        elif unit in ("million", "billion", "thousand"):
            plain.append(v * {"thousand": 1e3, "million": 1e6, "billion": 1e9}[unit])
        else:
            plain.append(v)
    return plain, pcts


def close(a: float, b: float, tol: float = REL_TOL) -> bool:
    if a == b:
        return True
    denom = max(abs(a), abs(b))
    return denom > 0 and abs(a - b) / denom <= tol


def score_turn(question: str, gold: float, our_text: str) -> tuple[bool, str]:
    """Deterministic numeric comparison (see module docstring).

    Gold values are raw table-cell magnitudes, so plain claims are compared
    under the same unit-equivalence convention the golden-set scoring uses
    (a table "in millions" may be quoted as "$12.5" or "$12.5 million").
    """
    if gold is None:
        return False, "no-gold"
    plain, pcts = numeric_claims(our_text)
    if _PERCENT_Q_RE.search(question):
        pool = [(v, gold * 100) for v in pcts + plain]
    else:
        pool = [(v, gold * r) for v in plain for r in (1.0, 1e3, 1e6, 1e9)]
        pool += [(v, gold * 100) for v in pcts]  # ratios phrased as percents
    for v, target in pool:
        if close(abs(v), abs(target)) or close(v, target):
            return True, "match"
    return False, ("refused" if not our_text.strip() else "wrong-number")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--limit", type=int, default=None, help="only the first N conversations (smoke runs)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="no LLM calls — verify parsing/scoring plumbing"
    )
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    if not DEV_PATH.exists():
        raise SystemExit(
            f"missing {DEV_PATH} — download data.zip from "
            "github.com/czyssrs/ConvFinQA into data/convfinqa/"
        )

    cfg = load_cfg(str(P3 / "config.toml"))
    pack = get_pack("financial")
    convs = load_conversations(args.limit)
    n_turns = sum(len(c["annotation"]["dialogue_break"]) for c in convs)
    print(
        f"ConvFinQA dev: {len(convs)} conversations, {n_turns} turns"
        + (" [DRY RUN — no LLM calls]" if args.dry_run else "")
    )

    out_path = (
        Path(args.out)
        if args.out
        else (P1 / "reports" / "convfinqa" / f"convfinqa_{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_correct = n_scored = n_refused = n_errors = 0
    convs_all_correct = 0

    with out_path.open("w", encoding="utf-8") as out:
        for ci, conv in enumerate(convs):
            ann = conv["annotation"]
            questions = ann["dialogue_break"]
            golds = ann["exe_ans_list"]
            hits = context_hits(conv)
            history: list[dict] = []
            turn_results = []

            for t, (q, gold) in enumerate(zip(questions, golds)):
                if args.dry_run:
                    rewritten, our, correct, how = q, "", gold is not None, "dry"
                else:
                    try:
                        rewritten = rewrite_followup(q, history, cfg, pack=pack)
                        res = answer(rewritten, hits, cfg, graph_rescue=None, pack=pack)
                    except Exception as e:  # noqa: BLE001
                        n_errors += 1
                        turn_results.append(
                            {"turn": t, "question": q, "error": f"{type(e).__name__}: {e}"[:200]}
                        )
                        print(
                            f"[{ci + 1}/{len(convs)}] t{t}: ERROR {type(e).__name__}: {str(e)[:80]}"
                        )
                        continue
                    our = res.get("answer") or ""
                    if res.get("refused"):
                        our = ""
                        n_refused += 1
                    correct, how = score_turn(q, gold, our)
                    rewritten = rewritten

                n_scored += 1
                n_correct += int(correct)
                turn_results.append(
                    {
                        "turn": t,
                        "question": q,
                        "rewritten": rewritten,
                        "gold": gold,
                        "our_answer": our,
                        "correct": correct,
                        "how": how,
                    }
                )
                history.append({"role": "user", "content": q})
                history.append({"role": "assistant", "content": our or "(no answer given)"})

            all_ok = bool(turn_results) and all(tr.get("correct") for tr in turn_results)
            convs_all_correct += int(all_ok)
            marks = "".join("+" if tr.get("correct") else "-" for tr in turn_results)
            print(f"[{ci + 1}/{len(convs)}] {conv.get('id', '')}: {marks}")
            out.write(
                json.dumps(
                    {
                        "conv_id": conv.get("id"),
                        "filename": conv.get("filename"),
                        "n_turns": len(questions),
                        "all_correct": all_ok,
                        "turns": turn_results,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            out.flush()

    print(
        f"\nConvFinQA: turn accuracy {n_correct}/{n_scored} = {n_correct / n_scored:.1%}"
        if n_scored
        else "\nno turns scored"
    )
    print(f"conversation accuracy (all turns correct): {convs_all_correct}/{len(convs)}")
    print(f"refusals: {n_refused} | errors: {n_errors}")
    print(f"results -> {out_path}")


if __name__ == "__main__":
    main()
