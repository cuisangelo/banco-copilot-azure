"""Run the reference dataset against a deployed copilot-api and write evals/report.md.

Usage: uv run --all-packages python -m evals.run --target https://<copilot-api>
Exits 1 when any forbidden value leaks, so CI can gate on it.
"""
import argparse
import json
import statistics
import sys
import uuid
from pathlib import Path

import httpx
from azure.ai.evaluation import GroundednessEvaluator, RetrievalEvaluator, SimilarityEvaluator
from azure.identity import DefaultAzureCredential

from bank_contracts.settings import require_env
from evals.client import CopilotClient
from evals.metrics import RowResult, citation_recall, find_leaks, summarize, tools_match

EVALS_DIR = Path(__file__).resolve().parent


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


def judge(row: dict, answer: dict, traces: list[dict], evaluators: dict) -> dict:
    if answer["status"] != "ok":
        return {}
    response = answer_text(answer)
    context = retrieved_context(traces)
    scores = {"similarity": evaluators["similarity"](query=row["question"], response=response,
                                                     ground_truth=row["expected_answer"])["similarity"]}
    if context:
        scores["groundedness"] = evaluators["groundedness"](query=row["question"], response=response,
                                                            context=context)["groundedness"]
        scores["retrieval"] = evaluators["retrieval"](query=row["question"], context=context)["retrieval"]
    return scores


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()

    model_config = {
        "azure_endpoint": require_env("AZURE_OPENAI_ENDPOINT"),
        "azure_deployment": require_env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
        "api_version": require_env("AZURE_OPENAI_API_VERSION"),
    }
    credential = DefaultAzureCredential()
    evaluators = {
        "similarity": SimilarityEvaluator(model_config, credential=credential),
        "groundedness": GroundednessEvaluator(model_config, credential=credential),
        "retrieval": RetrievalEvaluator(model_config, credential=credential),
    }
    client = CopilotClient(httpx.Client(base_url=args.target, timeout=120))
    rows = [json.loads(line) for line in (EVALS_DIR / "dataset.jsonl").read_text(encoding="utf-8").splitlines()]

    results, details = [], []
    raw = (EVALS_DIR / "results.jsonl").open("w", encoding="utf-8")
    for row in rows:
        try:
            answer, traces, error, latency = run_row(client, row)
        except httpx.HTTPError as exc:
            # One broken stream is a failed row, not a reason to lose the rest of the run.
            answer, traces, error, latency = None, [], {"code": f"transport:{type(exc).__name__}"}, 0
        raw.write(json.dumps({"id": row["id"], "answer": answer, "error": error, "traces": traces},
                             ensure_ascii=False) + "\n")
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
        scores = judge(row, answer, traces, evaluators) if answer else {}
        results.append(result)
        details.append({"id": row["id"], "type": row["type"], "expected": row["expected_status"], "got": status,
                        **scores, "leaks": result.leaks})
        print(f"{row['id']} {row['type']:28} {status:16} {'OK' if result.status_ok else 'MISS'}", flush=True)

    raw.close()
    summary = summarize(results)
    for key in ("similarity", "groundedness", "retrieval"):
        values = [d[key] for d in details if key in d]
        summary[key] = statistics.mean(values) if values else None
    write_report(summary, details)
    print(json.dumps(summary, indent=2))
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
