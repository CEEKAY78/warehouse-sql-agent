from wsa.retriever import Doc, Retriever, load_glossary

VOCAB = ["revenue", "net", "cancel", "customer", "active", "country", "month", "product"]


class WordCountEmbedder:
    """Deterministic stand-in for bge-m3: counts vocabulary words."""

    def __init__(self):
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return [[float(t.lower().count(w)) + 0.01 for w in VOCAB] for t in texts]


DOCS = [
    Doc(id="g:net_revenue", kind="glossary", title="Net revenue",
        text="Net revenue = sum of line_amount including cancel lines (revenue net of cancel)."),
    Doc(id="g:active_customer", kind="glossary", title="Active customer",
        text="An active customer bought in the last 90 days; customer table dim_customer."),
    Doc(id="e:1", kind="example", title="Revenue by country",
        text="Q: revenue by country\nSQL: SELECT country_name, sum(line_amount) ..."),
    Doc(id="e:2", kind="example", title="Products per month",
        text="Q: products sold per month\nSQL: SELECT month, count(DISTINCT product_key) ..."),
]


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
