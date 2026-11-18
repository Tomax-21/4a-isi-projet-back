# tests/test_products.py
from sqlmodel import select

from app.models import Product, User, UserRole
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


def create_product(session, name="Pizza", price="8.50", quantity=10, **options):
    product = Product(name=name, price=price, quantity=quantity, **options)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def product_json(**changes):
    """Corps JSON valide pour POST / PUT, modifiable champ par champ."""
    body = {
        "name": "Pizza",
        "description": "Margherita",
        "price": 8.5,
        "quantity": 10,
        "is_available": True,
    }
    body.update(changes)
    return body


# =====================================================================
# GET /products : lister (public)
# =====================================================================
def test_list_products_without_token(client, session):
    create_product(session, name="Pizza")
    create_product(session, name="Salade")
    r = client.get("/products")
    assert r.status_code == 200
    assert [p["name"] for p in r.json()] == ["Pizza", "Salade"]


def test_list_products_empty(client):
    r = client.get("/products")
    assert r.status_code == 200
    assert r.json() == []


def test_list_products_hides_deleted(client, session):
    create_product(session, name="Pizza")
    create_product(session, name="Ancien", is_deleted=True)
    names = [p["name"] for p in client.get("/products").json()]
    assert names == ["Pizza"]


def test_list_products_hides_is_deleted_field(client, session):
    create_product(session)
    product = client.get("/products").json()[0]
    assert "is_deleted" not in product


def test_list_products_price_is_a_number(client, session):
    create_product(session, price="8.50")
    assert client.get("/products").json()[0]["price"] == 8.5


# =====================================================================
# GET /products/{id} : détail (public)
# =====================================================================
def test_get_product_ok(client, session):
    product = create_product(session, name="Pizza", quantity=3)
    r = client.get(f"/products/{product.id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Pizza"
    assert r.json()["quantity"] == 3


def test_get_product_unknown(client):
    assert client.get("/products/9999").status_code == 404


def test_get_product_deleted(client, session):
    product = create_product(session, is_deleted=True)
    assert client.get(f"/products/{product.id}").status_code == 404


# =====================================================================
# POST /products : créer (admin)
# =====================================================================
def test_create_product_ok(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(), headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] is not None
    assert body["name"] == "Pizza"
    assert body["price"] == 8.5
    assert isinstance(body["price"], (int, float))   # un nombre, pas du texte

    in_db = session.exec(select(Product).where(Product.name == "Pizza")).first()
    assert in_db is not None


def test_create_product_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    r = client.post("/products", json=product_json(), headers=headers)
    assert r.status_code == 403


def test_create_product_without_token(client):
    r = client.post("/products", json=product_json())
    assert r.status_code == 401


def test_create_product_empty_name(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(name="   "), headers=headers)
    assert r.status_code == 400


def test_create_product_name_too_long(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(name="a" * 101), headers=headers)
    assert r.status_code == 400


def test_create_product_negative_price(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(price=-1), headers=headers)
    assert r.status_code == 400


def test_create_product_negative_quantity(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(quantity=-1), headers=headers)
    assert r.status_code == 400


def test_create_product_missing_field(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json={"name": "Pizza"}, headers=headers)
    assert r.status_code == 422


# =====================================================================
# PUT /products/{id} : modifier (admin)
# =====================================================================
def test_update_product_ok(client, session):
    headers = admin_header(client, session)
    product = create_product(session)
    r = client.put(
        f"/products/{product.id}",
        json=product_json(name="Pizza 4 fromages", price=11, quantity=2, is_available=False),
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Pizza 4 fromages"
    assert r.json()["price"] == 11
    assert isinstance(r.json()["price"], (int, float))
    assert r.json()["quantity"] == 2
    assert r.json()["is_available"] is False

    # la modification est bien enregistrée en base
    session.expire_all()
    assert session.get(Product, product.id).quantity == 2


def test_update_product_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    product = create_product(session)
    r = client.put(f"/products/{product.id}", json=product_json(), headers=headers)
    assert r.status_code == 403


def test_update_product_without_token(client, session):
    product = create_product(session)
    r = client.put(f"/products/{product.id}", json=product_json())
    assert r.status_code == 401


def test_update_product_unknown(client, session):
    headers = admin_header(client, session)
    r = client.put("/products/9999", json=product_json(), headers=headers)
    assert r.status_code == 404


def test_update_product_deleted(client, session):
    headers = admin_header(client, session)
    product = create_product(session, is_deleted=True)
    r = client.put(f"/products/{product.id}", json=product_json(), headers=headers)
    assert r.status_code == 404


def test_update_product_invalid_data(client, session):
    headers = admin_header(client, session)
    product = create_product(session)
    r = client.put(f"/products/{product.id}", json=product_json(price=-5), headers=headers)
    assert r.status_code == 400


# =====================================================================
# DELETE /products/{id} : supprimer (admin, soft delete)
# =====================================================================
def test_delete_product_ok(client, session):
    headers = admin_header(client, session)
    product = create_product(session)
    r = client.delete(f"/products/{product.id}", headers=headers)
    assert r.status_code == 204
    assert client.get(f"/products/{product.id}").status_code == 404
    assert client.get("/products").json() == []


def test_delete_product_is_a_soft_delete(client, session):
    # la ligne reste en base (les anciennes commandes la référencent)
    headers = admin_header(client, session)
    product = create_product(session)
    client.delete(f"/products/{product.id}", headers=headers)

    session.expire_all()
    in_db = session.get(Product, product.id)
    assert in_db is not None
    assert in_db.is_deleted is True


def test_delete_product_twice(client, session):
    headers = admin_header(client, session)
    product = create_product(session)
    client.delete(f"/products/{product.id}", headers=headers)
    r = client.delete(f"/products/{product.id}", headers=headers)
    assert r.status_code == 404


def test_delete_product_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    product = create_product(session)
    r = client.delete(f"/products/{product.id}", headers=headers)
    assert r.status_code == 403


def test_delete_product_without_token(client, session):
    product = create_product(session)
    assert client.delete(f"/products/{product.id}").status_code == 401


def test_delete_product_unknown(client, session):
    headers = admin_header(client, session)
    assert client.delete("/products/9999", headers=headers).status_code == 404




# =====================================================================
# Les espaces autour du nom sont supprimés (création ET modification)
# =====================================================================
def test_create_product_strips_name(client, session):
    headers = admin_header(client, session)
    r = client.post("/products", json=product_json(name="  Pizza  "), headers=headers)
    assert r.status_code == 201
    assert r.json()["name"] == "Pizza"


def test_update_product_strips_name(client, session):
    headers = admin_header(client, session)
    product = create_product(session)
    r = client.put(f"/products/{product.id}", json=product_json(name="  Pizza 4 fromages  "), headers=headers)
    assert r.status_code == 200
    assert r.json()["name"] == "Pizza 4 fromages"

    # et c'est bien le nom sans espaces qui est enregistré en base
    session.expire_all()
    assert session.get(Product, product.id).name == "Pizza 4 fromages"
