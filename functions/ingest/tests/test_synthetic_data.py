import json
import re
from pathlib import Path

from bank_contracts.models import LEVEL2_FIELDS, CustomerFields, CustomerProfile, Product

from chunker import chunk_document

DATA = Path(__file__).resolve().parents[3] / "data"
PROFILE_KEYS = set(CustomerProfile.model_fields)
PAYMENT_BEHAVIORS = {"al_dia", "atraso_30", "atraso_90"}
# Mirrors the minimum income stated in data/docs/ficha-credito-hipotecario.md §3.
MORTGAGE_MIN_INCOME_CLP = 1_200_000
REAL_BANK_NAMES = re.compile(
    r"BancoEstado|Banco ?Estado|Santander|\bBCI\b|Ita[uú]|Scotiabank|Banco de Chile|Falabella|Ripley|"
    r"\bBICE\b|Consorcio|Banco Security|Banco Internacional|Interbank",
    re.IGNORECASE,
)


def _products() -> list[dict]:
    return json.loads((DATA / "products.json").read_text())


def _customers() -> list[dict]:
    return json.loads((DATA / "customers.json").read_text())


def _docs() -> dict[str, str]:
    return {path.stem: path.read_text() for path in sorted((DATA / "docs").glob("*.md"))}


def test_every_product_validates_and_ids_are_unique():
    products = [Product.model_validate(p) for p in _products()]

    assert len({p.id for p in products}) == len(products) >= 8


def test_customers_are_c1001_to_c1020():
    assert [c["customer_id"] for c in _customers()] == [f"C-{n}" for n in range(1001, 1021)]


def test_customer_keys_are_exactly_profile_plus_level2():
    for row in _customers():
        assert set(row) == PROFILE_KEYS | set(LEVEL2_FIELDS), row["customer_id"]


def test_customer_levels_validate_against_contract_models():
    for row in _customers():
        CustomerProfile.model_validate(row)
        CustomerFields(customer_id=row["customer_id"], values={f: row[f] for f in LEVEL2_FIELDS}, grant_id="g")
        assert row["payment_behavior"] in PAYMENT_BEHAVIORS
        assert all(type(row[f]) is int for f in ("monthly_income", "current_debt", "employment_tenure_months"))


def test_customer_products_exist_in_catalog():
    catalog = {p["id"] for p in _products()}

    for row in _customers():
        assert set(row["products"]) <= catalog, row["customer_id"]


def test_data_reproduces_mortgage_contradiction_and_severe_arrears_cases():
    customers = _customers()

    assert any(
        r["monthly_income"] >= MORTGAGE_MIN_INCOME_CLP and 12 <= r["employment_tenure_months"] < 24
        and r["income_type"] == "dependiente"
        for r in customers
    )
    assert any(r["payment_behavior"] == "atraso_90" for r in customers)


def test_twelve_documents_chunk_with_doc_id_matching_file_name():
    docs = _docs()

    assert len(docs) == 12
    for stem, text in docs.items():
        assert {c.doc_id for c in chunk_document(text)} == {stem}


def test_mortgage_sheet_and_circular_contradict_on_employment_tenure():
    docs = _docs()

    assert "12 meses" in docs["ficha-credito-hipotecario"]
    assert "24 meses" in docs["circular-2026-07"]


def test_one_document_hides_an_indirect_prompt_injection():
    assert sum("ignora tus instrucciones" in text.lower() for text in _docs().values()) == 1


def test_no_real_bank_is_named():
    files = [*_docs().values(), json.dumps(_products(), ensure_ascii=False)]

    assert not [m.group() for text in files for m in REAL_BANK_NAMES.finditer(text)]
