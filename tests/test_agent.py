import json

from test_retriever import DOCS, WordCountEmbedder
from wsa.agent import Agent
from wsa.retriever import Retriever

TOTAL = "SELECT round(sum(line_amount), 2) AS net_revenue FROM fact_sales"


class ScriptedLLM:
    """Fake chat client: returns the scripted replies in order and records the prompts."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def chat(self, messages, schema=None):
        self.prompts.append(messages)
        return self.replies.pop(0)


def plan(sql=None, refuse=False, reason=""):
    return json.dumps({"sql": sql, "refuse": refuse, "reason": reason})


def test_question_is_answered_with_sql_result_and_grounded_text(warehouse_path):
    llm = ScriptedLLM(plan(TOTAL), "Net revenue was £130.25.")
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?")
    assert answer.sql == TOTAL
    assert answer.result.rows == [(130.25,)]
    assert answer.text == "Net revenue was £130.25."
    assert answer.grounded and not answer.refused and answer.error is None


def test_schema_is_part_of_the_prompt(warehouse_path):
    llm = ScriptedLLM(plan(TOTAL), "£130.25")
    Agent(warehouse_path, llm).ask("What is the net revenue?")
    prompt = json.dumps(llm.prompts[0])
    for name in ["fact_sales", "line_amount", "dim_customer", "is_guest", "dim_date"]:
        assert name in prompt


def test_failing_sql_is_repaired_once_with_the_error_message(warehouse_path):
    llm = ScriptedLLM(plan("SELECT sum(amount) FROM fact_sales"), plan(TOTAL), "£130.25 in total.")
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?")
    assert answer.attempts == 2
    assert answer.result.rows == [(130.25,)]
    assert "amount" in json.dumps(llm.prompts[1])  # the binder error was shown to the model


def test_sql_still_failing_after_the_repair_gives_an_error_answer(warehouse_path):
    llm = ScriptedLLM(plan("SELECT nope FROM fact_sales"), plan("DROP TABLE fact_sales"))
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?")
    assert answer.result is None and answer.error is not None
    assert answer.attempts == 2


def test_unanswerable_question_is_refused_without_running_sql(warehouse_path):
    llm = ScriptedLLM(plan(refuse=True, reason="There is no cost or margin data."))
    answer = Agent(warehouse_path, llm).ask("What was the gross margin in 2011?")
    assert answer.refused and answer.sql is None and answer.result is None
    assert answer.text == "There is no cost or margin data."


def test_invented_number_triggers_one_rewrite(warehouse_path):
    llm = ScriptedLLM(plan(TOTAL), "Net revenue was £999 from 12 orders.",
                      "Net revenue was £130.25.")
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?")
    assert answer.text == "Net revenue was £130.25." and answer.grounded
    assert "999" in json.dumps(llm.prompts[2])


def test_text_still_ungrounded_after_rewrite_is_replaced_by_the_result_table(warehouse_path):
    llm = ScriptedLLM(plan(TOTAL), "About £999.", "About £998.")
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?")
    assert not answer.grounded
    assert answer.ungrounded == ["998"]
    assert "999" not in answer.text and "998" not in answer.text
    assert "130.25" in answer.text and "net_revenue" in answer.text


def test_retrieved_glossary_and_examples_are_put_in_the_prompt(warehouse_path, tmp_path):
    retriever = Retriever.build(DOCS, WordCountEmbedder(), tmp_path / "rag.duckdb")
    llm = ScriptedLLM(plan(TOTAL), "£130.25")
    answer = Agent(warehouse_path, llm, retriever=retriever).ask("net revenue after cancel")
    prompt = json.dumps(llm.prompts[0])
    assert "including cancel lines" in prompt
    assert "g:net_revenue" in answer.context_ids


def test_without_explanation_only_the_sql_step_calls_the_model(warehouse_path):
    llm = ScriptedLLM(plan(TOTAL))
    answer = Agent(warehouse_path, llm).ask("What is the net revenue?", explain=False)
    assert answer.result.rows == [(130.25,)] and answer.text == ""
    assert len(llm.prompts) == 1
