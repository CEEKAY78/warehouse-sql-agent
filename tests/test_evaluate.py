import json

from wsa.agent import Answer
from wsa.evaluate import EvalQuestion, evaluate
from wsa.guard import run_readonly

TOTAL = "SELECT round(sum(line_amount), 2) FROM fact_sales"
BY_COUNTRY = ("SELECT country_name, round(sum(line_amount), 2) FROM fact_sales "
              "JOIN dim_country USING (country_key) GROUP BY 1")

QUESTIONS = [
    EvalQuestion("q1", "simple", "Net revenue?", TOTAL),
    EvalQuestion("q2", "join", "Revenue by country?", BY_COUNTRY),
    EvalQuestion("q3", "time", "Revenue in 2011?", "SELECT 20.25"),
    EvalQuestion("t1", "trap", "Gross margin?", None),
    EvalQuestion("t2", "trap", "Stock level?", None),
]


class FakeAgent:
    """Answers from a dict question -> sql | 'REFUSE'."""

    def __init__(self, db, plan):
        self.db, self.plan, self.calls = db, plan, []

    def ask(self, question, explain=True):
        self.calls.append(question)
        sql = self.plan[question]
        if sql == "REFUSE":
            return Answer(question=question, refused=True, text="no data")
        return Answer(question=question, sql=sql, result=run_readonly(self.db, sql), attempts=1)


def test_scores_per_category_and_counts_refusals_separately(warehouse_path, tmp_path):
    agent = FakeAgent(warehouse_path, {
        "Net revenue?": TOTAL,                                     # correct
        "Revenue by country?": "SELECT 'France', 20.25",           # wrong: one row missing
        "Revenue in 2011?": "REFUSE",                              # false refusal
        "Gross margin?": "REFUSE",                                 # correct refusal
        "Stock level?": "SELECT 1",                                # answered a trap
    })
    report = evaluate(agent, QUESTIONS, warehouse_path, tmp_path / "run.jsonl")
    assert report.by_category == {"simple": (1, 1), "join": (0, 1), "time": (0, 1),
                                  "trap": (1, 2)}
    assert report.correct == 2 and report.total == 5
    assert report.answerable_accuracy == 1 / 3
    assert report.false_refusals == 1
    assert report.trap_refusal_rate == 0.5


def test_each_question_is_written_to_jsonl_and_a_rerun_resumes(warehouse_path, tmp_path):
    out = tmp_path / "run.jsonl"
    plan = {q.question: (q.gold_sql or "REFUSE") for q in QUESTIONS}
    evaluate(FakeAgent(warehouse_path, plan), QUESTIONS[:2], warehouse_path, out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == ["q1", "q2"] and all(r["correct"] for r in rows)
    assert {"sql", "refused", "seconds", "error", "category"} <= set(rows[0])

    with out.open("a", encoding="utf-8") as f:
        f.write('{"id": "q3", "categ')  # the process died while writing this line
    agent = FakeAgent(warehouse_path, plan)
    report = evaluate(agent, QUESTIONS, warehouse_path, out)
    assert agent.calls == ["Revenue in 2011?", "Gross margin?", "Stock level?"]
    assert report.total == 5 and report.correct == 5
