# tests/test_closures.py
import datetime as dt

import pytest
from sqlmodel import select

from app.models import ClosedDay, User, UserRole
from app.security import hash_password


# ---------- Fonctions utiles ----------
def create_user(session, username="alice", password="1234", **options):
    user = User(username=username, password_hash=hash_password(password), **options)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def auth_header(client, username="alice", password="1234"):
    r = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def admin_header(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    return auth_header(client, username="admin")


def create_closure(session, date=dt.date(2026, 12, 25), reason="Noël"):
    closure = ClosedDay(date=date, reason=reason)
    session.add(closure)
    session.commit()
    session.refresh(closure)
    return closure


# =====================================================================
# GET /closures : lister (public)
# =====================================================================
def test_list_closures_without_token(client, session):
    create_closure(session, date=dt.date(2026, 12, 25), reason="Noël")
    r = client.get("/closures")
    assert r.status_code == 200
    assert r.json()[0]["date"] == "2026-12-25"
    assert r.json()[0]["reason"] == "Noël"


def test_list_closures_empty(client):
    r = client.get("/closures")
    assert r.status_code == 200
    assert r.json() == []


def test_list_closures_sorted_by_date(client, session):
    create_closure(session, date=dt.date(2027, 1, 1), reason="Nouvel an")
    create_closure(session, date=dt.date(2026, 12, 25), reason="Noël")
    dates = [c["date"] for c in client.get("/closures").json()]
    assert dates == ["2026-12-25", "2027-01-01"]


def test_list_closures_reason_can_be_null(client, session):
    create_closure(session, reason=None)
    assert client.get("/closures").json()[0]["reason"] is None


# =====================================================================
# GET /closures?date=AAAA-MM-JJ : filtrer à partir d'un jour
# =====================================================================
def create_three_closures(session):
    create_closure(session, date=dt.date(2026, 12, 25), reason="Noël")
    create_closure(session, date=dt.date(2027, 1, 1), reason="Nouvel an")
    create_closure(session, date=dt.date(2027, 5, 1), reason="1er mai")


def test_list_closures_filter_keeps_later_days(client, session):
    create_three_closures(session)
    r = client.get("/closures", params={"date": "2026-12-31"})
    assert r.status_code == 200
    assert [c["date"] for c in r.json()] == ["2027-01-01", "2027-05-01"]


def test_list_closures_filter_excludes_earlier_days(client, session):
    create_three_closures(session)
    r = client.get("/closures", params={"date": "2027-02-01"})
    assert [c["date"] for c in r.json()] == ["2027-05-01"]


def test_list_closures_filter_includes_the_day_itself(client, session):
    create_three_closures(session)
    r = client.get("/closures", params={"date": "2026-12-25"})
    assert [c["date"] for c in r.json()] == ["2026-12-25", "2027-01-01", "2027-05-01"]


def test_list_closures_filter_after_last_closure(client, session):
    create_three_closures(session)
    r = client.get("/closures", params={"date": "2030-01-01"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_closures_without_filter_returns_all(client, session):
    create_three_closures(session)
    assert len(client.get("/closures").json()) == 3


@pytest.mark.parametrize(
    "bad_date",
    ["pas-une-date", "25/12/2026", "2026-13-01", "2026-02-30", "20261225", ""],
    ids=repr,
)
def test_list_closures_filter_invalid_date(client, session, bad_date):
    create_three_closures(session)
    r = client.get("/closures", params={"date": bad_date})
    assert r.status_code == 422


# =====================================================================
# POST /closures : ajouter (admin)
# =====================================================================
def test_create_closure_ok(client, session):
    headers = admin_header(client, session)
    r = client.post("/closures", json={"date": "2026-12-25", "reason": "Noël"}, headers=headers)
    assert r.status_code == 201
    assert r.json()["id"] is not None
    assert r.json()["date"] == "2026-12-25"
    assert r.json()["reason"] == "Noël"

    in_db = session.exec(select(ClosedDay)).all()
    assert len(in_db) == 1


def test_create_closure_without_reason(client, session):
    headers = admin_header(client, session)
    r = client.post("/closures", json={"date": "2026-12-25", "reason": None}, headers=headers)
    assert r.status_code == 201
    assert r.json()["reason"] is None


def test_create_closure_already_closed(client, session):
    headers = admin_header(client, session)
    create_closure(session, date=dt.date(2026, 12, 25))
    r = client.post("/closures", json={"date": "2026-12-25", "reason": "Autre"}, headers=headers)
    assert r.status_code == 409


# Seul le format AAAA-MM-JJ est accepté. FastAPI refuse tout le reste avec une 422,
# sans qu'on écrive de vérification dans la route.
@pytest.mark.parametrize(
    "bad_date",
    [
        "pas-une-date",           # du texte
        "25/12/2026",             # format français
        "12-25-2026",             # format américain
        "20261225",               # sans séparateurs
        "2026-13-01",             # mois qui n'existe pas
        "2026-02-30",             # jour qui n'existe pas
        "2026-12-25T10:30:00",    # date + heure
        "2026-12-25 ",            # espace en trop
        "",                       # chaîne vide
        None,                     # null
        20261225,                 # nombre
        True,                     # booléen
        [],                       # liste
    ],
    ids=repr,
)
def test_create_closure_invalid_date_format(client, session, bad_date):
    headers = admin_header(client, session)
    r = client.post("/closures", json={"date": bad_date, "reason": "x"}, headers=headers)
    assert r.status_code == 422

    # et rien n'a été enregistré en base
    assert session.exec(select(ClosedDay)).all() == []


def test_create_closure_missing_date(client, session):
    headers = admin_header(client, session)
    r = client.post("/closures", json={"reason": "x"}, headers=headers)
    assert r.status_code == 422


def test_create_closure_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    r = client.post("/closures", json={"date": "2026-12-25", "reason": "Noël"}, headers=headers)
    assert r.status_code == 403


def test_create_closure_without_token(client):
    r = client.post("/closures", json={"date": "2026-12-25", "reason": "Noël"})
    assert r.status_code == 401


# =====================================================================
# DELETE /closures/{id} : supprimer (admin)
# =====================================================================
def test_delete_closure_ok(client, session):
    headers = admin_header(client, session)
    closure = create_closure(session)
    r = client.delete(f"/closures/{closure.id}", headers=headers)
    assert r.status_code == 204
    assert client.get("/closures").json() == []


def test_delete_closure_then_date_can_be_closed_again(client, session):
    headers = admin_header(client, session)
    closure = create_closure(session, date=dt.date(2026, 12, 25))
    client.delete(f"/closures/{closure.id}", headers=headers)
    r = client.post("/closures", json={"date": "2026-12-25", "reason": "Noël"}, headers=headers)
    assert r.status_code == 201


def test_delete_closure_unknown(client, session):
    headers = admin_header(client, session)
    assert client.delete("/closures/9999", headers=headers).status_code == 404


def test_delete_closure_twice(client, session):
    headers = admin_header(client, session)
    closure = create_closure(session)
    client.delete(f"/closures/{closure.id}", headers=headers)
    assert client.delete(f"/closures/{closure.id}", headers=headers).status_code == 404


def test_delete_closure_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    closure = create_closure(session)
    assert client.delete(f"/closures/{closure.id}", headers=headers).status_code == 403


def test_delete_closure_without_token(client, session):
    closure = create_closure(session)
    assert client.delete(f"/closures/{closure.id}").status_code == 401