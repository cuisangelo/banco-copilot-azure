import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KEYS = ["id", "type", "persona", "customer_id", "question", "expected_status", "expected_answer",
        "expected_citations", "expected_tools", "grant_fields", "forbidden_values"]
TYPES = {"respondible", "producto", "mixta", "cliente_nivel1", "cliente_nivel2_con_permiso",
         "cliente_nivel2_sin_permiso", "sin_respuesta", "contradictoria", "fuera_de_alcance",
         "injection_directa", "injection_indirecta", "escalada_por_injection", "ambigua"}
STATUSES = {"ok", "clarification", "insufficient", "contradiction", "rejected", "access_required"}
TOOLS = {"get_product", "list_products", "compare_products", "get_customer_profile", "get_customer_fields"}
LEVEL1 = {"segment", "income_type", "products", "customer_tenure_months"}
LEVEL2 = {"monthly_income", "current_debt", "payment_behavior", "employment_tenure_months"}


def load_reference_data():
    customers = {c["customer_id"] for c in json.loads((ROOT / "data/customers.json").read_text(encoding="utf-8"))}
    products = {p["id"] for p in json.loads((ROOT / "data/products.json").read_text(encoding="utf-8"))}
    docs = {}
    for path in (ROOT / "data/docs").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        doc_id = re.search(r"^doc_id:\s*(\S+)", text, re.M).group(1)
        docs[doc_id] = {h.strip() for h in re.findall(r"^## (.+)$", text, re.M)}
    return customers, products, docs


def row_errors(row, customers, products, docs):
    errors = []
    if list(row) != KEYS:
        errors.append(f"keys {list(row)}")
    if row["type"] not in TYPES:
        errors.append("type")
    if row["expected_status"] not in STATUSES:
        errors.append("status")
    if row["persona"] not in (None, "ana", "bruno", "sofia"):
        errors.append("persona")
    if row["type"].startswith("cliente_") and (row["persona"] not in ("ana", "bruno") or row["customer_id"] is None):
        errors.append("customer row needs an Asesor persona and a customer_id")
    if row["customer_id"] is not None and row["customer_id"] not in customers:
        errors.append(f"unknown customer {row['customer_id']}")
    if (row["expected_status"] == "rejected") != (row["expected_answer"] == ""):
        errors.append("expected_answer must be empty exactly when rejected")
    if not set(row["expected_tools"]) <= TOOLS:
        errors.append(f"tools {row['expected_tools']}")
    if row["type"] == "cliente_nivel2_con_permiso":
        if not row["grant_fields"] or not set(row["grant_fields"]) <= LEVEL2:
            errors.append("grant_fields")
    elif row["grant_fields"]:
        errors.append("grant_fields only for con_permiso rows")
    for value in row["forbidden_values"]:
        if value.lower() in row["expected_answer"].lower():
            errors.append(f"forbidden value {value!r} in expected_answer")
    for citation in row["expected_citations"]:
        if citation.startswith("producto:"):
            if citation[9:] not in products:
                errors.append(f"unknown product {citation}")
        elif citation.startswith("cliente:"):
            customer_id, field = citation[8:].split(" ", 1)
            if customer_id != row["customer_id"]:
                errors.append(f"cites another customer {citation}")
            if field not in LEVEL1 | LEVEL2:
                errors.append(f"unknown field {citation}")
            if field in LEVEL2 and field not in row["grant_fields"]:
                errors.append(f"cites ungranted level-2 field {citation}")
        else:
            doc_id, heading = citation.split(" §", 1)
            if heading not in docs.get(doc_id, set()):
                errors.append(f"unknown doc or heading {citation!r}")
    return errors


def test_dataset_matches_reference_data():
    customers, products, docs = load_reference_data()
    rows = [json.loads(line) for line in (ROOT / "evals/dataset.jsonl").read_text(encoding="utf-8").splitlines()]
    errors = [f"{r['id']}: {e}" for r in rows for e in row_errors(r, customers, products, docs)]
    assert [r["id"] for r in rows] == [f"e{i:02d}" for i in range(1, len(rows) + 1)]
    assert {r["type"] for r in rows} == TYPES
    assert errors == []
