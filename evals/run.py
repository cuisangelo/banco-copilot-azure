"""Run the reference dataset against a deployed copilot-api, grade it in Foundry and write evals/report.md.

Usage: uv run --all-packages python -m evals.run --target https://<copilot-api>
The graded run is uploaded to the Foundry project at FOUNDRY_PROJECT_ENDPOINT (Evaluations);
results.jsonl and report.md stay local. Exits 1 when any forbidden value leaks, so CI can gate on it.
"""
import argparse
import json
import math
import statistics
import sys
import uuid
from pathlib import Path

import httpx
from azure.ai.evaluation import GroundednessEvaluator, RetrievalEvaluator, SimilarityEvaluator, evaluate
from azure.identity import DefaultAzureCredential

from bank_contracts.settings import require_env
from evals.client import CopilotClient
from evals.metrics import RowResult, citation_recall, find_leaks, summarize, tools_match

EVALS_DIR = Path(__file__).resolve().parent
JUDGE_INPUTS = {
    "similarity": ("query", "response", "ground_truth"),
    "groundedness": ("query", "response", "context"),
    "retrieval": ("query", "context"),
}
MEASURED = ("status_ok", "citation_recall", "tools_ok", "leak")


class AnsweredOnly:
    """A Foundry judge that grades only rows carrying every input it needs.

    Refusals, errors and answers without retrieved context have nothing to grade: they get no score
    instead of an evaluator error that would abort the run.
    """

    def __init__(self, judge, metric: str):
        self._judge = judge
        self._metric = metric

    def __call__(self, *, query: str, response: str, context: str, ground_truth: str) -> dict:
        given = {"query": query, "response": response, "context": context, "ground_truth": ground_truth}
        inputs = {name: given[name] for name in JUDGE_INPUTS[self._metric]}
        if not all(inputs.values()):
            return {self._metric: None}
        return self._judge(**inputs)


class Measured:
    """Publishes a metric the runner already computed, so Foundry shows it beside the judges."""

    def __init__(self, metric: str):
        self._metric = metric

    def __call__(self, *, value: float | None) -> dict:
        return {self._metric: value}


def answer_text(answer: dict) -> str:
    claims = [c["text"] for c in answer.get("requirements", []) + answer.get("steps", [])]
    return "\n".join([answer.get("message", ""), *claims])


def retrieved_context(traces: list[dict]) -> str:
    chunks = [c for t in traces if t["node"] == "rag_agent" for c in t["data"].get("chunks", [])]
    return "\n\n".join(c["content"] for c in chunks)


def run_row(client: CopilotClient, row: dict):
    token = client.token(row["persona"]) if row["persona"] else None
    session_id = str(uuid.uuid4())
    answer, traces, error, latency = client.chat(token, session_id, row["question"], row["customer_id"])
    if row["type"] == "cliente_nivel2_con_permiso" and answer and answer["status"] == "access_required":
        client.decide_access(client.token("sofia"), answer["access_request"]["id"], row["grant_fields"])
        answer, more_traces, error, more_latency = client.resume(token, session_id)
        traces += more_traces
        latency += more_latency
    return answer, traces, error, latency


def evaluation_input(row: dict, result: RowResult, answer: dict | None, traces: list[dict]) -> dict:
    answered = answer is not None and answer["status"] == "ok"
    return {
        "id": row["id"], "type": row["type"], "query": row["question"], "ground_truth": row["expected_answer"],
        "response": answer_text(answer) if answered else "",
        "context": retrieved_context(traces) if answered else "",
        "status_ok": float(result.status_ok), "citation_recall": result.citation_recall,
        "tools_ok": float(result.tools_ok), "leak": len(result.leaks),
    }


def grade_in_foundry(inputs: list[dict], judges: dict, project_endpoint: str, credential) -> dict:
    run_dir = EVALS_DIR / ".run"
    run_dir.mkdir(exist_ok=True)
    data = run_dir / "data.jsonl"
    data.write_text("".join(json.dumps(i, ensure_ascii=False) + "\n" for i in inputs), encoding="utf-8")
    return evaluate(
        data=str(data),
        evaluators={m: AnsweredOnly(j, m) for m, j in judges.items()} | {m: Measured(m) for m in MEASURED},
        evaluator_config={m: {"column_mapping": {"value": f"${{data.{m}}}"}} for m in MEASURED},
        azure_ai_project=project_endpoint,
        credential=credential,
        evaluation_name="banco-copilot-referencia",
        fail_on_evaluator_errors=True,
    )


def judge_scores(graded_row: dict) -> dict:
    values = {m: graded_row.get(f"outputs.{m}.{m}") for m in JUDGE_INPUTS}
    return {m: None if v is None or math.isnan(v) else float(v) for m, v in values.items()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    project_endpoint = require_env("FOUNDRY_PROJECT_ENDPOINT")
    model_config = {
        "azure_endpoint": require_env("AZURE_OPENAI_ENDPOINT"),
        "azure_deployment": require_env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        "api_version": require_env("AZURE_OPENAI_API_VERSION"),
    }
    credential = DefaultAzureCredential()
    judges = {
        "similarity": SimilarityEvaluator(model_config, credential=credential),
        "groundedness": GroundednessEvaluator(model_config, credential=credential),
        "retrieval": RetrievalEvaluator(model_config, credential=credential),
    }
    client = CopilotClient(httpx.Client(base_url=args.target, timeout=120))
    rows = [json.loads(line) for line in (EVALS_DIR / "dataset.jsonl").read_text(encoding="utf-8").splitlines()]

    results, inputs, records, details = [], [], [], []
    # Written as rows arrive, so a failed Foundry upload does not lose the API calls already paid for.
    raw = (EVALS_DIR / "results.jsonl").open("w", encoding="utf-8")
    for row in rows:
        try:
            answer, traces, error, latency = run_row(client, row)
        except httpx.HTTPError as exc:
            # One broken stream is a failed row, not a reason to lose the rest of the run.
            answer, traces, error, latency = None, [], {"code": f"transport:{type(exc).__name__}"}, 0
        record = {"id": row["id"], "answer": answer, "error": error, "traces": traces, "latency_ms": latency}
        raw.write(json.dumps(record, ensure_ascii=False) + "\n")
        status = error["code"] if error else answer["status"]
        got_refs = [c["ref"] for c in answer.get("citations", [])] if answer else []
        result = RowResult(
            id=row["id"], type=row["type"], status_ok=status == row["expected_status"],
            citation_recall=citation_recall(row["expected_citations"], got_refs),
            tools_ok=tools_match(row["expected_tools"], traces),
            leaks=find_leaks(row["forbidden_values"], answer, traces), latency_ms=latency,
            tokens=sum(t["tokens_in"] + t["tokens_out"] for t in traces),
            cost_usd=sum(t["cost_usd"] for t in traces),
        )
        results.append(result)
        records.append(record)
        inputs.append(evaluation_input(row, result, answer, traces))
        details.append({"id": row["id"], "type": row["type"], "expected": row["expected_status"], "got": status,
                        "leaks": result.leaks})
        print(f"{row['id']} {row['type']:28} {status:16} {'OK' if result.status_ok else 'MISS'}", flush=True)
    raw.close()

    graded = grade_in_foundry(inputs, judges, project_endpoint, credential)
    with (EVALS_DIR / "results.jsonl").open("w", encoding="utf-8") as out:
        for record, detail, graded_row in zip(records, details, graded["rows"], strict=True):
            scores = judge_scores(graded_row)
            out.write(json.dumps(record | {"scores": scores}, ensure_ascii=False) + "\n")
            detail.update({m: v for m, v in scores.items() if v is not None})

    summary = summarize(results)
    for key in JUDGE_INPUTS:
        values = [d[key] for d in details if key in d]
        summary[key] = statistics.mean(values) if values else None
    write_report(summary, details)
    print(json.dumps(summary, indent=2))
    print(f"Foundry: {graded['studio_url']}")
    return 1 if summary["leak_count"] else 0


def write_report(summary: dict, details: list[dict]) -> None:
    lines = ["# Reporte de evaluación", "", "| Métrica | Valor |", "|---|---|"]
    lines += [f"| {k} | {v if not isinstance(v, float) else round(v, 4)} |" for k, v in summary.items()]
    lines += ["", "| Fila | Tipo | Esperado | Obtenido | Similarity | Groundedness | Retrieval | Fugas |",
              "|---|---|---|---|---|---|---|---|"]
    for d in details:
        lines.append(f"| {d['id']} | {d['type']} | {d['expected']} | {d['got']} | {d.get('similarity', '')} "
                     f"| {d.get('groundedness', '')} | {d.get('retrieval', '')} | {', '.join(d['leaks'])} |")
    (EVALS_DIR / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
