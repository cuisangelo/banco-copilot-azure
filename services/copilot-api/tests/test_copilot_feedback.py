RUT = "12.345.678-5"


def rate(client, personas, persona: str | None = None, **overrides):
    body = {"session_id": "s-1", "turn_index": 0, "rating": "up", "answer_status": "ok", **overrides}
    headers = {"Authorization": f"Bearer {personas.issue(persona)[0]}"} if persona else {}
    return client.post("/feedback", json=body, headers=headers)


def feedback_list(client, personas, persona: str = "sofia", **params):
    return client.get("/feedback", params=params, headers={"Authorization": f"Bearer {personas.issue(persona)[0]}"})


def test_anonymous_feedback_is_created(client, personas):
    response = rate(client, personas)

    assert response.status_code == 201
    assert response.json() == {"id": "feedback:anonymous:s-1:0"}


def test_the_same_actor_rates_a_turn_only_once(client, personas):
    assert rate(client, personas, "ana").status_code == 201
    assert rate(client, personas, "ana", rating="down").status_code == 409
    assert rate(client, personas, "bruno").status_code == 201
    assert rate(client, personas, "ana", turn_index=1).status_code == 201


def test_listing_feedback_requires_the_supervisor_role(client, personas):
    assert feedback_list(client, personas, "ana").status_code == 403
    assert client.get("/feedback").status_code == 401


def test_supervisor_lists_feedback_newest_first(client, personas):
    rate(client, personas, "ana", rating="down", comment="Faltó la cita del procedimiento", answer_status="insufficient")
    rate(client, personas, turn_index=1)

    response = feedback_list(client, personas)

    assert response.status_code == 200
    newest, oldest = response.json()
    assert (newest["actor"], newest["turn_index"], newest["rating"]) == ("anonymous", 1, "up")
    assert oldest["actor"] == "ana"
    assert oldest["comment"] == "Faltó la cita del procedimiento"
    assert oldest["answer_status"] == "insufficient"
    assert [item["created_at"] for item in feedback_list(client, personas, limit=1).json()] == [newest["created_at"]]


def test_comment_is_stored_with_pii_masked(client, personas):
    rate(client, personas, "ana", rating="down", comment=f"El cliente {RUT} no aparece")

    (stored,) = feedback_list(client, personas).json()

    assert RUT not in stored["comment"]
    assert stored["comment"] == "El cliente [RUT] no aparece"


def test_feedback_keeps_no_answer_text(client, personas):
    rate(client, personas, "ana", message="La renta mensual informada es 1850000.")

    (stored,) = feedback_list(client, personas).json()

    assert set(stored) == {"id", "actor", "created_at", "session_id", "turn_index", "rating", "comment", "answer_status"}


def test_feedback_shares_the_rate_limit(client, personas):
    statuses = [rate(client, personas, turn_index=index).status_code for index in range(11)]

    assert statuses == [201] * 10 + [429]
