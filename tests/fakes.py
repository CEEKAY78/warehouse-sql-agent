"""Fakes at the external boundaries only: the chat model and the embedding model."""

from wsa.retriever import Doc

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



class ScriptedLLM:
    """Fake chat client: returns the scripted replies in order and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def chat(self, messages, schema=None):
        self.prompts.append(messages)
        return self.replies.pop(0)
