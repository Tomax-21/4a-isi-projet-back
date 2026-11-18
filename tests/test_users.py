# tests/test_users.py
from sqlmodel import select

from app.models import User, UserRole
from app.security import hash_password


# ---------- Fonctions utiles ----------
def create_user(session, username="alice", password="1234", **options):
    """Crée un utilisateur directement en base (role = USER par défaut)."""
    user = User(username=username, password_hash=hash_password(password), **options)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def auth_header(client, username="alice", password="1234"):
    """Se connecte et renvoie le header à joindre aux routes protégées."""
    r = client.post("/auth/login", json={"username": username, "password": password})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# =====================================================================
# POST /users : créer un compte
# =====================================================================
def test_create_user_ok(client):
    r = client.post("/users", json={"username": "bob"})
    assert r.status_code == 201
    body = r.json()
    assert body["username"] == "bob"
    assert body["id"] is not None
    assert body["password"] != ""


def test_create_user_generated_password_works(client):
    # le mot de passe renvoyé doit permettre de se connecter
    password = client.post("/users", json={"username": "bob"}).json()["password"]
    r = client.post("/auth/login", json={"username": "bob", "password": password})
    assert r.status_code == 200


def test_create_user_must_change_password(client, session):
    client.post("/users", json={"username": "bob"})
    user = session.exec(select(User).where(User.username == "bob")).first()
    assert user.must_change_password is True


def test_create_user_password_is_hashed(client, session):
    password = client.post("/users", json={"username": "bob"}).json()["password"]
    user = session.exec(select(User).where(User.username == "bob")).first()
    assert user.password_hash != password   # jamais stocké en clair


def test_create_user_empty_username(client):
    r = client.post("/users", json={"username": "   "})
    assert r.status_code == 400


def test_create_user_username_too_long(client):
    r = client.post("/users", json={"username": "a" * 51})
    assert r.status_code == 400


def test_create_user_already_taken(client, session):
    create_user(session, username="bob")
    r = client.post("/users", json={"username": "bob"})
    assert r.status_code == 409


def test_create_user_missing_field(client):
    r = client.post("/users", json={})
    assert r.status_code == 422   # FastAPI refuse tout seul


# =====================================================================
# PATCH /users/me/password : changer son mot de passe
# =====================================================================
def test_change_password_ok(client, session):
    create_user(session)
    headers = auth_header(client)

    r = client.patch(
        "/users/me/password",
        json={"old_password": "1234", "new_password": "nouveau123"},
        headers=headers,
    )
    assert r.status_code == 200

    # l'ancien mot de passe ne marche plus, le nouveau oui
    old = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    new = client.post("/auth/login", json={"username": "alice", "password": "nouveau123"})
    assert old.status_code == 401
    assert new.status_code == 200


def test_change_password_resets_must_change_password(client, session):
    create_user(session, must_change_password=True)
    headers = auth_header(client)

    client.patch(
        "/users/me/password",
        json={"old_password": "1234", "new_password": "nouveau123"},
        headers=headers,
    )
    session.expire_all()   # force la relecture en base
    user = session.exec(select(User).where(User.username == "alice")).first()
    assert user.must_change_password is False


def test_change_password_wrong_old_password(client, session):
    create_user(session)
    headers = auth_header(client)
    r = client.patch(
        "/users/me/password",
        json={"old_password": "faux", "new_password": "nouveau123"},
        headers=headers,
    )
    assert r.status_code == 400


def test_change_password_too_short(client, session):
    create_user(session)
    headers = auth_header(client)
    r = client.patch(
        "/users/me/password",
        json={"old_password": "1234", "new_password": "abc"},
        headers=headers,
    )
    assert r.status_code == 400


def test_change_password_without_token(client):
    r = client.patch(
        "/users/me/password",
        json={"old_password": "1234", "new_password": "nouveau123"},
    )
    assert r.status_code == 401


# =====================================================================
# GET /users : lister les utilisateurs (admin)
# =====================================================================
def test_list_users_as_admin(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    create_user(session, username="alice")
    headers = auth_header(client, username="admin")

    r = client.get("/users", headers=headers)
    assert r.status_code == 200
    usernames = [u["username"] for u in r.json()]
    assert "admin" in usernames
    assert "alice" in usernames


def test_list_users_hides_password_hash(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    headers = auth_header(client, username="admin")

    r = client.get("/users", headers=headers)
    for user in r.json():
        assert "password_hash" not in user


def test_list_users_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    r = client.get("/users", headers=headers)
    assert r.status_code == 403


def test_list_users_without_token(client):
    r = client.get("/users")
    assert r.status_code == 401


# =====================================================================
# PATCH /users/{id}/block : bloquer / débloquer (admin)
# =====================================================================
def test_block_user_ok(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    alice = create_user(session, username="alice")
    headers = auth_header(client, username="admin")

    r = client.patch(f"/users/{alice.id}/block", json={"is_blocked": True}, headers=headers)
    assert r.status_code == 200
    assert r.json()["is_blocked"] is True

    # alice ne peut plus se connecter
    login = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert login.status_code == 403


def test_unblock_user(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    alice = create_user(session, username="alice", is_blocked=True)
    headers = auth_header(client, username="admin")

    r = client.patch(f"/users/{alice.id}/block", json={"is_blocked": False}, headers=headers)
    assert r.status_code == 200
    assert r.json()["is_blocked"] is False

    login = client.post("/auth/login", json={"username": "alice", "password": "1234"})
    assert login.status_code == 200


def test_block_takes_effect_immediately(client, session):
    # alice est connectée et possède déjà un token valide
    create_user(session, username="admin", role=UserRole.ADMIN)
    alice = create_user(session, username="alice")
    alice_headers = auth_header(client, username="alice")
    admin_headers = auth_header(client, username="admin")

    client.patch(f"/users/{alice.id}/block", json={"is_blocked": True}, headers=admin_headers)

    # son ancien token est maintenant refusé
    r = client.patch(
        "/users/me/password",
        json={"old_password": "1234", "new_password": "nouveau123"},
        headers=alice_headers,
    )
    assert r.status_code == 403


def test_admin_cannot_block_himself(client, session):
    admin = create_user(session, username="admin", role=UserRole.ADMIN)
    headers = auth_header(client, username="admin")
    r = client.patch(f"/users/{admin.id}/block", json={"is_blocked": True}, headers=headers)
    assert r.status_code == 400


def test_block_unknown_user(client, session):
    create_user(session, username="admin", role=UserRole.ADMIN)
    headers = auth_header(client, username="admin")
    r = client.patch("/users/9999/block", json={"is_blocked": True}, headers=headers)
    assert r.status_code == 404


def test_block_forbidden_for_standard_user(client, session):
    create_user(session, username="alice")
    bob = create_user(session, username="bob")
    headers = auth_header(client, username="alice")
    r = client.patch(f"/users/{bob.id}/block", json={"is_blocked": True}, headers=headers)
    assert r.status_code == 403


def test_block_without_token(client, session):
    bob = create_user(session, username="bob")
    r = client.patch(f"/users/{bob.id}/block", json={"is_blocked": True})
    assert r.status_code == 401