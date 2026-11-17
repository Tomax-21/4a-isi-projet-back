import pytest
from app.models import User, UserRole
from app.security import hash_password


def create_user(session, username="alice", password="1234", **options):
    user = User(username=username, password_hash=hash_password(password), **options)
    session.add(user)
    session.commit()
    return user

def login(client, username="alice", password="1234"):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_login_ok(client, session):
    create_user(session)
    r = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert r.status_code == 200
    assert "access_token" in r.json()
    assert r.json()["role"] == "user"


def test_login_admin(client, session):
    create_user(session, role="admin")
    r = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"

def test_login_admin2(client, session):
    create_user(session, role=UserRole.ADMIN)
    r = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_login_invalid_role(client, session):
    with pytest.raises(Exception):
        create_user(session, role="n_importe_quoi")
        login(client)


def test_login_unknown_user(client):
    r = client.post("/auth/login", json={"username": "personne", "password": "1234"})
    assert r.status_code == 401


def test_login_blocked_user(client, session):
    create_user(session, is_blocked=True)
    r = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert r.status_code == 403