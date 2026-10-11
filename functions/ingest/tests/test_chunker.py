from datetime import date

import pytest

from chunker import chunk_document

THREE_SECTIONS = """---
doc_id: ficha-demo
title: Ficha Demo
valid_from: 2026-03-01
---

# Ficha Demo

## 1. Descripción

Producto de prueba.

## 2. Requisitos

- Renta mínima de $500.000.
- Cédula de identidad vigente.

## 3. Condiciones

Plazo de 12 a 60 meses.
"""


def test_three_sections_produce_three_chunks_with_metadata():
    chunks = chunk_document(THREE_SECTIONS)

    assert [c.section for c in chunks] == ["1. Descripción", "2. Requisitos", "3. Condiciones"]
    assert {(c.doc_id, c.doc_title, c.valid_from) for c in chunks} == {
        ("ficha-demo", "Ficha Demo", date(2026, 3, 1))
    }
    assert chunks[1].content == "- Renta mínima de $500.000.\n- Cédula de identidad vigente."


def test_chunk_ids_are_stable_across_runs():
    first = [c.id for c in chunk_document(THREE_SECTIONS)]
    second = [c.id for c in chunk_document(THREE_SECTIONS)]

    assert first == second == ["ficha-demo-0", "ficha-demo-1", "ficha-demo-2"]


def test_long_section_splits_into_overlapping_windows():
    words = [f"w{i}" for i in range(1000)]
    text = THREE_SECTIONS.replace("Producto de prueba.", " ".join(words))

    chunks = chunk_document(text, max_words=800, overlap=100)
    description = [c for c in chunks if c.section == "1. Descripción"]

    assert len(description) == 2
    assert description[0].content.split() == words[:800]
    assert description[1].content.split() == words[700:]
    assert [c.id for c in chunks] == [f"ficha-demo-{n}" for n in range(4)]


def test_missing_front_matter_key_fails():
    with pytest.raises(ValueError, match="valid_from"):
        chunk_document(THREE_SECTIONS.replace("valid_from: 2026-03-01\n", ""))


def test_text_outside_a_section_fails():
    with pytest.raises(ValueError, match="before the first"):
        chunk_document(THREE_SECTIONS.replace("# Ficha Demo\n", "# Ficha Demo\n\nTexto suelto.\n"))
