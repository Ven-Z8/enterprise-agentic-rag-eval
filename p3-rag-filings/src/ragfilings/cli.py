"""CLI entry point.

    ragfilings parse corpus/AAPL_2025-10-31_10K.htm   # section tree of one filing
    ragfilings index                                   # parse + chunk + embed corpus
    ragfilings ask "What was Apple's FY2025 net sales?" [--strategy hybrid]

Evaluation lives in the sibling p1-eval-harness project (`eval-harness run`).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import config as cfg_mod
from . import ingestion
from .pipeline import ask


def _cmd_parse(args: argparse.Namespace) -> None:
    cfg = cfg_mod.load(args.config)
    sections = ingestion.parse_file(
        args.filing,
        cfg["ingestion"]["min_section_chars"],
        cfg["ingestion"]["pointer_chars"],
    )
    print(f"{Path(args.filing).name}: {len(sections)} sections\n")
    print(ingestion.render_tree(sections))


def _cmd_index(args: argparse.Namespace) -> None:
    """Parse every filing in the manifest, chunk, and build the embedding index."""
    from . import chunking, retrieval  # lazy: pulls in torch

    cfg = cfg_mod.load(args.config)
    root = cfg_mod.ROOT
    ing = cfg["ingestion"]
    chunks_dir = root / "corpus" / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    all_chunks = []
    with (root / cfg["corpus"]["manifest"]).open() as f:
        for m in csv.DictReader(f):
            path = root / "corpus" / m["local_file"]
            if not path.exists():
                print(
                    f"skip {m['ticker']}: {path.name} missing (run scripts/download_corpus.py)",
                    file=sys.stderr,
                )
                continue
            sections = ingestion.parse_file(path, ing["min_section_chars"], ing["pointer_chars"])
            chunks = chunking.chunk_sections(sections, m, cfg["chunking"]["max_chars"])
            with (chunks_dir / f"{m['ticker']}_chunks.jsonl").open("w", encoding="utf-8") as out:
                for c in chunks:
                    out.write(json.dumps(c, ensure_ascii=False) + "\n")
            all_chunks.extend(chunks)
            print(f"{m['ticker']:<6} {len(chunks):>5} chunks")
    print(
        f"\nembedding {len(all_chunks)} chunks with {cfg['embedding']['model']} (first run downloads the model)..."
    )
    retrieval.build_index(
        all_chunks, root / cfg["embedding"]["index_dir"], cfg["embedding"]["model"]
    )
    print(f"index written to {cfg['embedding']['index_dir']}")


def _cmd_ask(args: argparse.Namespace) -> None:
    cfg = cfg_mod.load(args.config)
    result = ask(args.question, cfg, strategy=args.strategy, domain=args.domain)
    print(
        f"strategy={result['strategy']} confidence={result['confidence']:.3f} "
        f"latency={result['latency_ms'] / 1000:.1f}s "
        f"cost=${result['usage']['cost_usd']:.4f}\n"
    )
    if result["refused"]:
        print(f"REFUSED: {result['refusal_reason']}")
        return
    print(result["answer"])
    print("\ncitations:")
    for c in result["citations"]:
        print(f"  {c}")
    ver = result["verification"]
    if not ver["verified"]:
        failed = ", ".join(c["raw"] for c in ver["claims"] if not c["found"])
        print(f"\n⚠️ verification FAILED for: {failed}")


def _cmd_graph(args: argparse.Namespace) -> None:
    """Build (and optionally LLM-summarize) the fact graph + communities."""
    from . import retrieval
    from .graph import FinancialGraphBuilder

    cfg = cfg_mod.load(args.config)
    root = cfg_mod.ROOT
    index = retrieval.load_index(root / cfg["embedding"]["index_dir"], cfg["embedding"]["model"])
    builder = FinancialGraphBuilder()
    builder.build_from_chunks(index.chunks)
    builder.build_communities(index.chunks)
    if args.summarize:
        n = builder.summarize_communities(cfg, max_communities=args.max_summaries)
        print(f"summarized {n} communities via [extraction] model")
    out = root / "corpus" / "graph" / "financial_graph.json"
    builder.save(out)
    print(
        f"graph: {builder.graph.number_of_nodes()} nodes, "
        f"{builder.graph.number_of_edges()} edges, "
        f"{len(builder.communities)} communities -> {out}"
    )


def _cmd_serve(args: argparse.Namespace) -> None:
    """Launch the modern 3-panel UI and live Agent Swarm visualizer."""
    import uvicorn

    from .ui.server import app

    print(f"Starting RAGFilings Intelligence UI at http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


def main() -> None:
    p = argparse.ArgumentParser(prog="ragfilings")
    p.add_argument("--config", default=None, help="path to config.toml")
    sub = p.add_subparsers(dest="cmd", required=True)

    parse = sub.add_parser("parse", help="parse one filing, print its section tree")
    parse.add_argument("filing", help="path to a 10-K .htm file")
    parse.set_defaults(func=_cmd_parse)

    index = sub.add_parser("index", help="parse + chunk + embed the whole corpus")
    index.set_defaults(func=_cmd_index)

    ask_cmd = sub.add_parser("ask", help="answer one question with citations")
    ask_cmd.add_argument("question")
    ask_cmd.add_argument(
        "--strategy",
        choices=[
            "dense",
            "hybrid",
            "hybrid_rerank",
            "agent_react",
            "dense_graph",
            "hybrid_graph",
            "hybrid_rerank_graph",
        ],
        default=None,
        help="override config [retrieval] strategy; *_graph adds fact-graph augmentation",
    )
    from .domains import available_packs

    ask_cmd.add_argument(
        "--domain",
        choices=list(available_packs()),
        default="financial",
        help="domain skill pack supplying prompts, fact layer, and claim semantics",
    )
    ask_cmd.set_defaults(func=_cmd_ask)

    graph = sub.add_parser("graph", help="build the fact graph + communities")
    graph.add_argument(
        "--summarize",
        action="store_true",
        help="LLM-summarize the largest communities (costs API calls)",
    )
    graph.add_argument("--max-summaries", type=int, default=12)
    graph.set_defaults(func=_cmd_graph)

    serve_cmd = sub.add_parser("serve", help="launch the 3-panel Web UI & Swarm Visualizer")
    serve_cmd.add_argument("--host", default="127.0.0.1", help="host to bind")
    serve_cmd.add_argument("--port", type=int, default=8000, help="port to bind")
    serve_cmd.set_defaults(func=_cmd_serve)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
