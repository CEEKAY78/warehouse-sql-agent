from fakes import DOCS, WordCountEmbedder
from wsa.retriever import Retriever, load_glossary


def test_search_returns_the_most_similar_documents_of_a_kind(tmp_path):
    r = Retriever.build(DOCS, WordCountEmbedder(), tmp_path / "rag.duckdb")
    assert [d.id for d in r.search("What is the net revenue after cancel?", k=1,
                                   kind="glossary")] == ["g:net_revenue"]
    assert [d.id for d in r.search("how many active customer accounts", k=1,
                                   kind="glossary")] == ["g:active_customer"]
    assert [d.id for d in r.search("revenue per country", k=1, kind="example")] == ["e:1"]


def test_index_is_persisted_and_reopened_without_re_embedding_documents(tmp_path):
    path = tmp_path / "rag.duckdb"
    Retriever.build(DOCS, WordCountEmbedder(), path)
    embedder = WordCountEmbedder()
    r = Retriever(path, embedder)
    assert [d.id for d in r.search("products by month", k=1, kind="example")] == ["e:2"]
    assert embedder.calls == 1  # only the question was embedded


def test_precomputed_embeddings_are_used_without_calling_the_model(tmp_path):
    from wsa.retriever import CachedEmbedder

    inner = WordCountEmbedder()
    cached = CachedEmbedder(inner)
    cached.warm(["revenue per country", "products by month"])
    assert inner.calls == 1
    assert cached.embed(["products by month"]) == inner.embed(["products by month"])
    assert inner.calls == 2  # only the direct inner call above
    cached.embed(["something new"])
    assert inner.calls == 3


def test_glossary_markdown_is_split_into_one_doc_per_heading(tmp_path):
    md = tmp_path / "glossary.md"
    md.write_text("# Glossary\n\n## Net revenue\nSum of line_amount.\n\n## Order\nOne invoice.\n",
                  encoding="utf-8")
    docs = load_glossary(md)
    assert [(d.id, d.title, d.text) for d in docs] == [
        ("g:net-revenue", "Net revenue", "Sum of line_amount."),
        ("g:order", "Order", "One invoice."),
    ]
