from evals.client import parse_sse
from evals.metrics import RowResult, citation_recall, find_leaks, summarize, tools_match


def test_parse_sse_collects_traces_and_final_answer():
    stream = [
        "event: trace",
        'data: {"node": "router", "duration_ms": 5, "data": {"route": "procedure"}, "tokens_in": 10, "tokens_out": 2, "cost_usd": 0.1}',
        "",
        "event: answer",
        'data: {"status": "ok", "message": "hola", "citations": []}',
        "",
    ]
    answer, traces, error = parse_sse(stream)
    assert answer["status"] == "ok"
    assert [t["node"] for t in traces] == ["router"]
    assert error is None


def test_parse_sse_returns_error_event():
    answer, traces, error = parse_sse(["event: error", 'data: {"code": "token_cap", "message": "x"}', ""])
    assert answer is None
    assert error["code"] == "token_cap"


def test_citation_recall_counts_expected_refs_found():
    assert citation_recall(["a §1", "b §2"], ["a §1", "z §9"]) == 0.5
    assert citation_recall([], ["a §1"]) is None


def test_tools_match_compares_sets_of_called_tools():
    traces = [{"node": "product_agent", "data": {"tool_calls": [{"tool": "get_product"}, {"tool": "get_product"}]}}]
    assert tools_match(["get_product"], traces)
    assert not tools_match(["compare_products"], traces)
    assert tools_match([], [{"node": "router", "data": {}}])


def test_find_leaks_searches_answer_and_traces_case_insensitively():
    answer = {"message": "La renta es 1.450.000"}
    traces = [{"node": "customer_agent", "data": {"note": "ATRASO_90"}}]
    assert find_leaks(["1.450.000", "atraso_90", "3200000"], answer, traces) == ["1.450.000", "atraso_90"]


def test_find_leaks_ignores_the_digits_of_trace_counters():
    # A value can only leak through text: a cost of 0.00025560000000000003 is not the income 560000.
    traces = [{"node": "product_agent", "data": {}, "tokens_in": 435, "tokens_out": 51, "cost_usd": 0.00025560000000000003}]
    assert find_leaks(["560000"], {"message": "ok"}, traces) == []


def test_summarize_reports_leaks_and_status_accuracy():
    rows = [
        RowResult(id="e01", type="respondible", status_ok=True, citation_recall=1.0, tools_ok=True,
                  leaks=[], latency_ms=100, tokens=50, cost_usd=0.01),
        RowResult(id="e02", type="cliente_nivel2_sin_permiso", status_ok=False, citation_recall=None,
                  tools_ok=True, leaks=["1450000"], latency_ms=300, tokens=70, cost_usd=0.02),
    ]
    summary = summarize(rows)
    assert summary["leak_count"] == 1
    assert summary["status_accuracy"] == 0.5
    assert summary["citation_recall"] == 1.0
    assert summary["latency_p50_ms"] == 100


class FakeClient:
    def __init__(self):
        self.calls = []

    def token(self, persona):
        return f"tok-{persona}"

    def chat(self, token, session_id, message, customer_id):
        self.calls.append(("chat", token))
        answer = {"status": "access_required", "access_request": {"id": "ar-1"}}
        return answer, [{"node": "customer_agent", "data": {}}], None, 10

    def decide_access(self, supervisor_token, request_id, fields):
        self.calls.append(("decide", supervisor_token, request_id, tuple(fields)))

    def resume(self, token, session_id):
        self.calls.append(("resume", token))
        return {"status": "ok", "citations": []}, [{"node": "composer", "data": {}}], None, 20


def test_run_row_approves_as_supervisor_and_resumes_for_granted_rows():
    from evals.run import run_row

    client = FakeClient()
    row = {"type": "cliente_nivel2_con_permiso", "persona": "ana", "question": "q", "customer_id": "C-1007",
           "grant_fields": ["monthly_income"]}
    answer, traces, error, latency = run_row(client, row)
    assert answer["status"] == "ok"
    assert client.calls == [("chat", "tok-ana"), ("decide", "tok-sofia", "ar-1", ("monthly_income",)),
                            ("resume", "tok-ana")]
    assert [t["node"] for t in traces] == ["customer_agent", "composer"]
    assert latency == 30
