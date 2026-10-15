"""Command line: build the RAG index, ask one question, or run the evaluation.

    python -m wsa.cli index
    python -m wsa.cli ask "Which 5 countries had the highest net revenue?" [--model M] [--no-rag]
    python -m wsa.cli eval --model qwen2.5-coder:7b [--no-rag] [--limit 3] [--out PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wsa.agent import Agent, result_table
from wsa.evaluate import evaluate, load_questions
from wsa.ollama import OllamaChat, OllamaEmbedder
from wsa.retriever import CachedEmbedder, Retriever, load_examples, load_glossary

ROOT = Path(__file__).resolve().parents[2]
WAREHOUSE = ROOT / "data" / "warehouse.duckdb"
RAG = ROOT / "data" / "rag.duckdb"
DEFAULT_MODEL = "qwen2.5-coder:7b"


def build_index() -> Retriever:
    docs = load_glossary(ROOT / "knowledge" / "glossary.md") + [
        d for d in load_examples(ROOT / "knowledge" / "examples.jsonl")
    ]
    retriever = Retriever.build(docs, OllamaEmbedder(), RAG)
    print(f"indexed {len(docs)} documents -> {RAG}")
    return retriever


def make_agent(model: str, rag: bool) -> Agent:
    retriever = None
    if rag:
        retriever = Retriever(RAG, OllamaEmbedder()) if RAG.exists() else build_index()
    return Agent(WAREHOUSE, OllamaChat(model), retriever=retriever)


def run_slug(model: str, rag: bool) -> str:
    return model.replace(":", "_").replace("/", "_") + ("_rag" if rag else "_norag")


def main(argv: list[str] | None = None) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="wsa")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("index")
    ask = sub.add_parser("ask")
    ask.add_argument("question")
    ev = sub.add_parser("eval")
    ev.add_argument("--limit", type=int, default=None)
    ev.add_argument("--out", type=Path, default=None)
    ev.add_argument("--explain", action="store_true", help="also generate and check the prose")
    for p in (ask, ev):
        p.add_argument("--model", default=DEFAULT_MODEL)
        p.add_argument("--no-rag", action="store_true")
    args = parser.parse_args(argv)

    if args.cmd == "index":
        build_index()
        return
    agent = make_agent(args.model, rag=not args.no_rag)
    if args.cmd == "ask":
        a = agent.ask(args.question)
        print(f"SQL:\n{a.sql}\n" if a.sql else "")
        if a.result is not None:
            print(result_table(a.result, max_rows=15) + "\n")
        print(("REFUSED: " if a.refused else "") + (a.text or a.error or ""))
        if a.context_ids:
            print(f"\ncontext: {', '.join(a.context_ids)}")
        return

    questions = load_questions(ROOT / "eval" / "questions.jsonl")[: args.limit]
    if agent.retriever is not None:
        cached = CachedEmbedder(agent.retriever.embedder)
        cached.warm([q.question for q in questions])
        agent.retriever.embedder = cached
    out = args.out or ROOT / "eval" / "runs" / f"{run_slug(args.model, not args.no_rag)}.jsonl"
    report = evaluate(agent, questions, WAREHOUSE, out, explain=args.explain)
    print(f"{args.model} rag={not args.no_rag}: {report.correct}/{report.total} correct")
    for cat, (ok, n) in sorted(report.by_category.items()):
        print(f"  {cat:7s} {ok}/{n}")
    print(f"  answerable accuracy {report.answerable_accuracy:.0%}, false refusals "
          f"{report.false_refusals}, trap refusal rate {report.trap_refusal_rate:.0%}")
    print(f"written {out}")


if __name__ == "__main__":
    main()
