import json
import shutil
import subprocess
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parents[1]


def trace(node, data, cost=0.0002):
    return {"node": node, "duration_ms": 10, "data": data, "tokens_in": 100, "tokens_out": 20, "cost_usd": cost}


def sample_result(row):
    """One results.jsonl line shaped like evals.run writes it; e02 fails in transport, e03 is ungrounded."""
    if row["id"] == "e02":
        return {"id": "e02", "answer": None, "error": {"code": "transport:ReadTimeout"}, "traces": [],
                "latency_ms": 0, "scores": {"similarity": None, "groundedness": None, "retrieval": None}}
    status = "insufficient" if row["id"] == "e03" else row["expected_status"]
    traces = [trace("router", {"route": "procedure"}),
              trace("rag_agent", {"chunks": [{"content": "texto"}]}),
              trace("product_agent", {"tool_calls": [{"tool": tool} for tool in row["expected_tools"]]}),
              trace("verifier", {"uncited_claims": 0, "contradiction": None,
                                 "ungrounded_percentage": 0.4 if row["id"] == "e03" else 0.0})]
    answered = status == "ok"
    return {"id": row["id"], "answer": {"status": status, "message": "respuesta", "citations": []}, "error": None,
            "traces": traces, "latency_ms": 4000 + int(row["id"][1:]) * 100,
            "scores": {m: 4.0 if answered else None for m in ("similarity", "groundedness", "retrieval")}}


def test_report_notebook_executes_on_sample_results(tmp_path):
    (tmp_path / "notebooks").mkdir()
    shutil.copy(EVALS_DIR / "notebooks/reporte.ipynb", tmp_path / "notebooks")
    shutil.copy(EVALS_DIR / "dataset.jsonl", tmp_path)
    rows = [json.loads(line) for line in (EVALS_DIR / "dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    (tmp_path / "results.jsonl").write_text(
        "".join(json.dumps(sample_result(r), ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")

    subprocess.run(
        ["uv", "run", "--all-packages", "--group", "notebook", "jupyter", "nbconvert", "--execute",
         "--to", "notebook", "--output", str(tmp_path / "executed.ipynb"), str(tmp_path / "notebooks/reporte.ipynb")],
        check=True, cwd=EVALS_DIR.parent,
    )

    cells = json.loads((tmp_path / "executed.ipynb").read_text(encoding="utf-8"))["cells"]
    outputs = [o for c in cells if c["cell_type"] == "code" for o in c["outputs"]]
    assert not [o for o in outputs if o["output_type"] == "error"]
    failures = "".join(line for o in cells[-1]["outputs"] if o["output_type"] == "stream" for line in o["text"])
    assert "e01" not in failures
    assert "transport:ReadTimeout" in failures
    assert "verificador" in failures and "0.4" in failures
