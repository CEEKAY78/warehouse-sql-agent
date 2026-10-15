"""Small RAG index over the metric glossary and the few-shot question -> SQL examples.

Vectors live in their own DuckDB file (``data/rag.duckdb``), never in the warehouse, so the
SQL written by the model can only ever see the star schema. Similarity is cosine, computed by
DuckDB (``list_cosine_similarity``); a few hundred documents need no vector index.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import duckdb


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


@dataclass(frozen=True)
class Doc:
    id: str
    kind: str  # "glossary" | "example"
    title: str
    text: str


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def load_glossary(path: Path) -> list[Doc]:
    """One document per ``## heading`` section of a markdown file."""
    docs = []
    for block in re.split(r"^## ", Path(path).read_text(encoding="utf-8"), flags=re.M)[1:]:
        title, _, body = block.partition("\n")
        docs.append(Doc(id=f"g:{_slug(title)}", kind="glossary", title=title.strip(),
                        text=body.strip()))
    return docs


def load_examples(path: Path) -> list[Doc]:
    """Few-shot examples, one JSON object per line: {"id", "question", "sql"}."""
    docs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            ex = json.loads(line)
            docs.append(Doc(id=f"e:{ex['id']}", kind="example", title=ex["question"],
                            text=f"Q: {ex['question']}\nSQL: {ex['sql']}"))
    return docs


class Retriever:
    def __init__(self, path: Path, embedder: Embedder):
        self.path = Path(path)
        self.embedder = embedder

    @classmethod
    def build(cls, docs: list[Doc], embedder: Embedder, path: Path) -> Retriever:
        path = Path(path)
        if path.exists():
            path.unlink()
        vectors = embedder.embed([f"{d.title}\n{d.text}" for d in docs])
        con = duckdb.connect(str(path))
        try:
            con.execute(
                "CREATE TABLE docs (id VARCHAR, kind VARCHAR, title VARCHAR, text VARCHAR, "
                "embedding DOUBLE[])"
            )
            con.executemany(
                "INSERT INTO docs VALUES (?, ?, ?, ?, ?)",
                [(d.id, d.kind, d.title, d.text, v) for d, v in zip(docs, vectors, strict=True)],
            )
        finally:
            con.close()
        return cls(path, embedder)

    def search(self, question: str, k: int = 3, kind: str | None = None) -> list[Doc]:
        query = self.embedder.embed([question])[0]
        con = duckdb.connect(str(self.path), read_only=True)
        try:
            rows = con.execute(
                """
                SELECT id, kind, title, text FROM docs
                WHERE ? IS NULL OR kind = ?
                ORDER BY list_cosine_similarity(embedding, ?::DOUBLE[]) DESC, id
                LIMIT ?
                """,
                [kind, kind, query, k],
            ).fetchall()
        finally:
            con.close()
        return [Doc(*row) for row in rows]
