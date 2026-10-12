import json
import sys

import azure.ai.evaluation._evaluate._evaluate as sdk_evaluate
import pytest

from evals import run

PROJECT = "https://bcopilot-test-foundry.services.ai.azure.com/api/projects/bcopilot-project"
DATASET = [
    {"id": "e01", "type": "respondible", "persona": "ana", "customer_id": None, "question": "¿Requisitos del Oro?",
     "expected_status": "ok", "expected_answer": "Renta mínima de 1.200.000.",
     "expected_citations": ["ficha-tarjeta-oro §Requisitos"], "expected_tools": [], "grant_fields": [],
     "forbidden_values": ["3200000"]},
    {"id": "e02", "type": "fuera_de_alcance", "persona": None, "customer_id": None, "question": "¿Clima mañana?",
     "expected_status": "rejected", "expected_answer": "", "expected_citations": [], "expected_tools": [],
     "grant_fields": [], "forbidden_values": []},
]
ANSWERS = {
    "¿Requisitos del Oro?": {
        "status": "ok", "message": "Necesitas renta mínima.",
        "requirements": [{"text": "Renta de 1.200.000", "citation_ids": ["S1"]}], "steps": [],
        "citations": [{"id": "S1", "kind": "doc", "ref": "ficha-tarjeta-oro §Requisitos", "snippet": "renta"}],
    },
    "¿Clima mañana?": {"status": "rejected", "message": "Fuera de alcance."},
}
TRACES = {
    "¿Requisitos del Oro?": [{"node": "rag_agent", "duration_ms": 9, "tokens_in": 100, "tokens_out": 20,
                             "cost_usd": 0.001, "data": {"chunks": [{"content": "Renta mínima 1.200.000"}]}}],
    "¿Clima mañana?": [{"node": "router", "duration_ms": 3, "tokens_in": 30, "tokens_out": 2, "cost_usd": 0.0001,
                       "data": {"route": "out_of_scope"}}],
}


class FakeClient:
    def __init__(self, http, retrieval_mode):
        pass

    def token(self, persona):
        return f"tok-{persona}"

    def chat(self, token, session_id, message, customer_id):
        return ANSWERS[message], TRACES[message], None, 1200


class FakeJudge:
    """Stands in for a Foundry LLM judge; records what it was asked to grade."""

    instances = {}

    def __init__(self, metric):
        self.metric, self.calls = metric, []
        FakeJudge.instances[metric] = self

    def __call__(self, **inputs):
        self.calls.append(inputs)
        return {self.metric: 4.0, f"{self.metric}_reason": "fake"}


@pytest.fixture
def evals_dir(tmp_path, monkeypatch):
    (tmp_path / "dataset.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in DATASET) + "\n",
                                            encoding="utf-8")
    monkeypatch.setattr(run, "EVALS_DIR", tmp_path)
    monkeypatch.setattr(run, "CopilotClient", FakeClient)
    monkeypatch.setattr(run, "DefaultAzureCredential", lambda: "credential")
    for metric, name in [("similarity", "SimilarityEvaluator"), ("groundedness", "GroundednessEvaluator"),
                         ("retrieval", "RetrievalEvaluator")]:
        monkeypatch.setattr(run, name, lambda model_config, credential, metric=metric: FakeJudge(metric))
    monkeypatch.setattr(sys, "argv", ["evals.run", "--target", "http://copilot"])
    for name in ("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_CHAT_DEPLOYMENT", "AZURE_OPENAI_API_VERSION"):
        monkeypatch.setenv(name, "x")
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", PROJECT)
    return tmp_path


def test_run_is_uploaded_to_the_foundry_project_and_kept_locally(evals_dir, monkeypatch):
    uploads = []

    def capture_upload(metrics, instance_results, project, evaluation_name, name_map, **kwargs):
        uploads.append({"metrics": metrics, "rows": instance_results.to_dict("records"), "project": project,
                        "credential": kwargs.get("credential")})
        return "https://ai.azure.com/evaluation/run-1"

    monkeypatch.setattr(sdk_evaluate, "_log_metrics_and_instance_results_onedp", capture_upload)

    assert run.main() == 0

    [upload] = uploads
    assert upload["project"] == PROJECT
    assert upload["credential"] == "credential"
    measured = ("status_ok", "citation_recall", "tools_ok", "leak")
    assert {f"{m}.{m}" for m in (*run.JUDGE_INPUTS, *measured)} <= set(upload["metrics"])
    assert upload["metrics"]["status_ok.status_ok"] == 1.0
    assert [r["inputs.id"] for r in upload["rows"]] == ["e01", "e02"]

    # The rejected row has no answer to grade, so no judge is billed for it.
    assert FakeJudge.instances["similarity"].calls == [{
        "query": "¿Requisitos del Oro?", "response": "Necesitas renta mínima.\nRenta de 1.200.000",
        "ground_truth": "Renta mínima de 1.200.000."}]
    assert FakeJudge.instances["retrieval"].calls == [{"query": "¿Requisitos del Oro?",
                                                       "context": "Renta mínima 1.200.000"}]

    data = [json.loads(line) for line in (evals_dir / ".run/data.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [d["response"] for d in data] == ["Necesitas renta mínima.\nRenta de 1.200.000", ""]

    results = [json.loads(line) for line in (evals_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    assert results[0]["scores"] == {"similarity": 4.0, "groundedness": 4.0, "retrieval": 4.0}
    assert results[1]["scores"] == {"similarity": None, "groundedness": None, "retrieval": None}
    assert results[0]["latency_ms"] == 1200
    assert "| groundedness | 4.0 |" in (evals_dir / "report.md").read_text(encoding="utf-8")


def test_run_refuses_to_start_without_a_foundry_project(evals_dir, monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT")
    monkeypatch.setattr(run, "CopilotClient", lambda http: pytest.fail("called the API without a Foundry project"))

    with pytest.raises(RuntimeError, match="FOUNDRY_PROJECT_ENDPOINT"):
        run.main()
