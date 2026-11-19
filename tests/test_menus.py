# tests/test_menus.py
import datetime as dt

import pytest
from sqlmodel import select

from app.models import Menu, Product, User, UserRole
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


def create_menu(session, products=None, name="Menu midi", price="12.00", **options):
    menu = Menu(name=name, price=price, products=products or [], **options)
    session.add(menu)
    session.commit()
    session.refresh(menu)
    return menu


def menu_json(product_ids, **changes):
    """Corps JSON valide pour POST, modifiable champ par champ."""
    body = {
        "name": "Menu midi",
        "description": "Plat + dessert",
        "price": 12.5,
        "is_available": True,
        "start_date": None,
        "end_date": None,
        "product_ids": product_ids,
    }
    body.update(changes)
    return body


# =====================================================================
# GET /menus : lister (public)
# =====================================================================
def test_list_menus_without_token(client, session):
    pizza = create_product(session)
    create_menu(session, products=[pizza], name="Menu midi")
    r = client.get("/menus")
    assert r.status_code == 200
    assert r.json()[0]["name"] == "Menu midi"
    assert r.json()[0]["products"] == [{"id": pizza.id, "name": "Pizza"}]


def test_list_menus_empty(client):
    r = client.get("/menus")
    assert r.status_code == 200
    assert r.json() == []


def test_list_menus_hides_deleted(client, session):
    pizza = create_product(session)
    create_menu(session, products=[pizza], name="Menu midi")
    create_menu(session, products=[pizza], name="Ancien", is_deleted=True)
    assert [m["name"] for m in client.get("/menus").json()] == ["Menu midi"]


def test_list_menus_hides_is_deleted_field(client, session):
    create_menu(session, products=[create_product(session)])
    assert "is_deleted" not in client.get("/menus").json()[0]


def test_list_menus_price_is_a_number(client, session):
    create_menu(session, products=[create_product(session)], price="12.50")
    price = client.get("/menus").json()[0]["price"]
    assert isinstance(price, (int, float))
    assert price == 12.5


# Produits supprimés : volontairement conservés dans le menu
def test_list_menus_shows_deleted_products_inside_menu(client, session):
    pizza = create_product(session, name="Pizza")
    old = create_product(session, name="Ancien plat", is_deleted=True)
    create_menu(session, products=[pizza, old])
    products = client.get("/menus").json()[0]["products"]
    assert sorted(p["name"] for p in products) == ["Ancien plat", "Pizza"]


def test_list_menus_without_filter_returns_unavailable_menus_too(client, session):
    pizza = create_product(session)
    create_menu(session, products=[pizza], name="Actif")
    create_menu(session, products=[pizza], name="Désactivé", is_available=False)
    assert len(client.get("/menus").json()) == 2


# ---------- GET /menus?date=AAAA-MM-JJ ----------
def test_list_menus_filter_permanent_menu_is_always_available(client, session):
    create_menu(session, products=[create_product(session)], name="Permanent")
    for day in ["2020-01-01", "2026-11-18", "2099-12-31"]:
        r = client.get("/menus", params={"date": day})
        assert [m["name"] for m in r.json()] == ["Permanent"]


def test_list_menus_filter_day_menu(client, session):
    create_menu(
        session,
        products=[create_product(session)],
        name="Menu du jour",
        start_date=dt.date(2026, 11, 18),
        end_date=dt.date(2026, 11, 18),
    )
    assert len(client.get("/menus", params={"date": "2026-11-18"}).json()) == 1
    assert client.get("/menus", params={"date": "2026-11-17"}).json() == []
    assert client.get("/menus", params={"date": "2026-11-19"}).json() == []


def test_list_menus_filter_week_menu_includes_both_ends(client, session):
    create_menu(
        session,
        products=[create_product(session)],
        name="Menu de la semaine",
        start_date=dt.date(2026, 11, 16),
        end_date=dt.date(2026, 11, 22),
    )
    for day in ["2026-11-16", "2026-11-19", "2026-11-22"]:
        assert len(client.get("/menus", params={"date": day}).json()) == 1
    for day in ["2026-11-15", "2026-11-23"]:
        assert client.get("/menus", params={"date": day}).json() == []


def test_list_menus_filter_only_start_date_means_no_end(client, session):
    create_menu(session, products=[create_product(session)], name="Sans fin",
                start_date=dt.date(2026, 11, 16))
    assert client.get("/menus", params={"date": "2026-11-15"}).json() == []
    assert len(client.get("/menus", params={"date": "2026-11-16"}).json()) == 1
    assert len(client.get("/menus", params={"date": "2099-12-31"}).json()) == 1


def test_list_menus_filter_only_end_date_means_no_start(client, session):
    create_menu(session, products=[create_product(session)], name="Sans début",
                end_date=dt.date(2026, 11, 22))
    assert len(client.get("/menus", params={"date": "2020-01-01"}).json()) == 1
    assert len(client.get("/menus", params={"date": "2026-11-22"}).json()) == 1
    assert client.get("/menus", params={"date": "2026-11-23"}).json() == []


def test_list_menus_filter_excludes_unavailable_menus(client, session):
    create_menu(session, products=[create_product(session)], name="Désactivé", is_available=False)
    assert client.get("/menus", params={"date": "2026-11-18"}).json() == []


def test_list_menus_filter_mixes_menus(client, session):
    pizza = create_product(session)
    create_menu(session, products=[pizza], name="Permanent")
    create_menu(session, products=[pizza], name="Semaine prochaine",
                start_date=dt.date(2026, 11, 23), end_date=dt.date(2026, 11, 29))
    names = [m["name"] for m in client.get("/menus", params={"date": "2026-11-18"}).json()]
    assert names == ["Permanent"]


@pytest.mark.parametrize("bad_date", ["pas-une-date", "25/12/2026", "2026-13-01", "2026-02-30", ""], ids=repr)
def test_list_menus_filter_invalid_date(client, session, bad_date):
    r = client.get("/menus", params={"date": bad_date})
    assert r.status_code == 422


# =====================================================================
# GET /menus/{id} : détail (public)
# =====================================================================
def test_get_menu_ok(client, session):
    pizza = create_product(session, name="Pizza")
    salade = create_product(session, name="Salade")
    menu = create_menu(session, products=[pizza, salade], name="Menu midi")
    r = client.get(f"/menus/{menu.id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Menu midi"
    assert sorted(p["name"] for p in r.json()["products"]) == ["Pizza", "Salade"]


def test_get_menu_unknown(client):
    assert client.get("/menus/9999").status_code == 404


def test_get_menu_deleted(client, session):
    menu = create_menu(session, products=[create_product(session)], is_deleted=True)
    assert client.get(f"/menus/{menu.id}").status_code == 404


# =====================================================================
# POST /menus : créer (admin)
# =====================================================================
def test_create_menu_ok(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session, name="Pizza")
    salade = create_product(session, name="Salade")

    r = client.post("/menus", json=menu_json([pizza.id, salade.id]), headers=headers)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] is not None
    assert body["name"] == "Menu midi"
    assert body["price"] == 12.5
    assert sorted(p["name"] for p in body["products"]) == ["Pizza", "Salade"]

    # bien enregistré en base, avec ses produits
    session.expire_all()
    in_db = session.exec(select(Menu)).all()
    assert len(in_db) == 1
    assert len(in_db[0].products) == 2


def test_create_menu_permanent_has_no_dates(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id]), headers=headers)
    assert r.json()["start_date"] is None
    assert r.json()["end_date"] is None


def test_create_menu_with_dates(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post(
        "/menus",
        json=menu_json([pizza.id], start_date="2026-11-16", end_date="2026-11-22"),
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["start_date"] == "2026-11-16"
    assert r.json()["end_date"] == "2026-11-22"


def test_create_menu_one_day(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post(
        "/menus",
        json=menu_json([pizza.id], start_date="2026-11-18", end_date="2026-11-18"),
        headers=headers,
    )
    assert r.status_code == 201


def test_create_menu_then_visible_in_public_list(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    client.post("/menus", json=menu_json([pizza.id]), headers=headers)
    assert len(client.get("/menus").json()) == 1


def test_create_menu_duplicate_product_ids_are_merged(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id, pizza.id]), headers=headers)
    assert r.status_code == 201
    assert len(r.json()["products"]) == 1


def test_create_menu_strips_name(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], name="  Menu midi  "), headers=headers)
    assert r.json()["name"] == "Menu midi"


def test_create_menu_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id]), headers=headers)
    assert r.status_code == 403


def test_create_menu_without_token(client, session):
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id]))
    assert r.status_code == 401


def test_create_menu_empty_name(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], name="   "), headers=headers)
    assert r.status_code == 400


def test_create_menu_name_too_long(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], name="a" * 101), headers=headers)
    assert r.status_code == 400


# Prix : seul un prix négatif est refusé
@pytest.mark.parametrize("bad_price", [-1, -0.01], ids=repr)
def test_create_menu_invalid_price(client, session, bad_price):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], price=bad_price), headers=headers)
    assert r.status_code == 400


def test_create_menu_free_price_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], price=0), headers=headers)
    assert r.status_code == 201
    assert r.json()["price"] == 0


def test_create_menu_without_products(client, session):
    headers = admin_header(client, session)
    r = client.post("/menus", json=menu_json([]), headers=headers)
    assert r.status_code == 400


def test_create_menu_unknown_product(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id, 9999]), headers=headers)
    assert r.status_code == 404


# Produits supprimés : volontairement acceptés
def test_create_menu_with_deleted_product_is_accepted(client, session):
    headers = admin_header(client, session)
    old = create_product(session, is_deleted=True)
    r = client.post("/menus", json=menu_json([old.id]), headers=headers)
    assert r.status_code == 201
    assert [p["id"] for p in r.json()["products"]] == [old.id]


def test_create_menu_error_saves_nothing(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    client.post("/menus", json=menu_json([pizza.id, 9999]), headers=headers)   # 404
    assert session.exec(select(Menu)).all() == []


# Dates : une seule date est autorisée
def test_create_menu_only_start_date_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], start_date="2026-11-16"), headers=headers)
    assert r.status_code == 201
    assert r.json()["start_date"] == "2026-11-16"
    assert r.json()["end_date"] is None


def test_create_menu_only_end_date_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post("/menus", json=menu_json([pizza.id], end_date="2026-11-22"), headers=headers)
    assert r.status_code == 201
    assert r.json()["start_date"] is None
    assert r.json()["end_date"] == "2026-11-22"


def test_create_menu_start_after_end(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post(
        "/menus",
        json=menu_json([pizza.id], start_date="2026-11-22", end_date="2026-11-16"),
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.parametrize("bad_date", ["pas-une-date", "25/12/2026", "2026-13-01", "2026-02-30", 20261225], ids=repr)
def test_create_menu_invalid_date_format(client, session, bad_date):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.post(
        "/menus",
        json=menu_json([pizza.id], start_date=bad_date, end_date="2026-11-22"),
        headers=headers,
    )
    assert r.status_code == 422


def test_create_menu_missing_field(client, session):
    headers = admin_header(client, session)
    r = client.post("/menus", json={"name": "Menu"}, headers=headers)
    assert r.status_code == 422


# =====================================================================
# DELETE /menus/{id} : supprimer (admin, soft delete)
# =====================================================================
def test_delete_menu_ok(client, session):
    headers = admin_header(client, session)
    menu = create_menu(session, products=[create_product(session)])
    r = client.delete(f"/menus/{menu.id}", headers=headers)
    assert r.status_code == 204
    assert client.get(f"/menus/{menu.id}").status_code == 404
    assert client.get("/menus").json() == []


def test_delete_menu_is_a_soft_delete(client, session):
    headers = admin_header(client, session)
    menu = create_menu(session, products=[create_product(session)])
    client.delete(f"/menus/{menu.id}", headers=headers)

    session.expire_all()
    in_db = session.get(Menu, menu.id)
    assert in_db is not None
    assert in_db.is_deleted is True


def test_delete_menu_keeps_its_products(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    client.delete(f"/menus/{menu.id}", headers=headers)
    assert client.get(f"/products/{pizza.id}").status_code == 200


def test_delete_menu_twice(client, session):
    headers = admin_header(client, session)
    menu = create_menu(session, products=[create_product(session)])
    client.delete(f"/menus/{menu.id}", headers=headers)
    assert client.delete(f"/menus/{menu.id}", headers=headers).status_code == 404


def test_delete_menu_unknown(client, session):
    headers = admin_header(client, session)
    assert client.delete("/menus/9999", headers=headers).status_code == 404


def test_delete_menu_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    menu = create_menu(session, products=[create_product(session)])
    assert client.delete(f"/menus/{menu.id}", headers=headers).status_code == 403


def test_delete_menu_without_token(client, session):
    menu = create_menu(session, products=[create_product(session)])
    assert client.delete(f"/menus/{menu.id}").status_code == 401


# =====================================================================
# PUT /menus/{id} : modifier (admin)
# =====================================================================
def test_update_menu_ok(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session, name="Pizza")
    salade = create_product(session, name="Salade")
    menu = create_menu(session, products=[pizza], name="Ancien nom")

    r = client.put(
        f"/menus/{menu.id}",
        json=menu_json([salade.id], name="Nouveau nom", price=15.0),
        headers=headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == menu.id
    assert body["name"] == "Nouveau nom"
    assert body["price"] == 15.0
    assert [p["name"] for p in body["products"]] == ["Salade"]

    session.expire_all()
    in_db = session.get(Menu, menu.id)
    assert in_db.name == "Nouveau nom"
    assert [p.name for p in in_db.products] == ["Salade"]


def test_update_menu_replaces_all_products(client, session):
    headers = admin_header(client, session)
    a = create_product(session, name="A")
    b = create_product(session, name="B")
    c = create_product(session, name="C")
    menu = create_menu(session, products=[a, b])
    r = client.put(f"/menus/{menu.id}", json=menu_json([b.id, c.id]), headers=headers)
    assert sorted(p["name"] for p in r.json()["products"]) == ["B", "C"]


def test_update_menu_strips_name(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], name="  Menu soir  "), headers=headers)
    assert r.json()["name"] == "Menu soir"


def test_update_menu_duplicate_product_ids_are_merged(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id, pizza.id]), headers=headers)
    assert r.status_code == 200
    assert len(r.json()["products"]) == 1


def test_update_menu_set_dates(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(
        f"/menus/{menu.id}",
        json=menu_json([pizza.id], start_date="2026-11-16", end_date="2026-11-22"),
        headers=headers,
    )
    assert r.status_code == 200
    assert r.json()["start_date"] == "2026-11-16"
    assert r.json()["end_date"] == "2026-11-22"


def test_update_menu_back_to_permanent(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza],
                       start_date=dt.date(2026, 11, 16), end_date=dt.date(2026, 11, 22))
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id]), headers=headers)
    assert r.json()["start_date"] is None
    assert r.json()["end_date"] is None


def test_update_menu_disable_hides_it_from_date_filter(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], is_available=False), headers=headers)
    assert client.get("/menus", params={"date": "2026-11-18"}).json() == []


def test_update_menu_does_not_touch_other_menus(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza], name="Menu 1")
    other = create_menu(session, products=[pizza], name="Menu 2")
    client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], name="Modifié"), headers=headers)
    assert client.get(f"/menus/{other.id}").json()["name"] == "Menu 2"


def test_update_menu_forbidden_for_standard_user(client, session):
    create_user(session)
    headers = auth_header(client)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id]), headers=headers)
    assert r.status_code == 403


def test_update_menu_without_token(client, session):
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id]))
    assert r.status_code == 401


def test_update_menu_unknown(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    r = client.put("/menus/9999", json=menu_json([pizza.id]), headers=headers)
    assert r.status_code == 404


def test_update_menu_deleted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza], is_deleted=True)
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id]), headers=headers)
    assert r.status_code == 404


def test_update_menu_unknown_product(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id, 9999]), headers=headers)
    assert r.status_code == 404


# Produits supprimés : volontairement acceptés
def test_update_menu_with_deleted_product_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    old = create_product(session, name="Vieux", is_deleted=True)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([old.id]), headers=headers)
    assert r.status_code == 200
    assert [p["id"] for p in r.json()["products"]] == [old.id]


def test_update_menu_error_changes_nothing(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza], name="Original")
    client.put(f"/menus/{menu.id}", json=menu_json([pizza.id, 9999], name="Changé"), headers=headers)  # 404
    session.expire_all()
    in_db = session.get(Menu, menu.id)
    assert in_db.name == "Original"
    assert [p.id for p in in_db.products] == [pizza.id]


@pytest.mark.parametrize("bad_name", ["   ", "", "a" * 101], ids=repr)
def test_update_menu_invalid_name(client, session, bad_name):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], name=bad_name), headers=headers)
    assert r.status_code == 400


# Prix : seul un prix négatif est refusé
@pytest.mark.parametrize("bad_price", [-1, -0.01], ids=repr)
def test_update_menu_invalid_price(client, session, bad_price):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], price=bad_price), headers=headers)
    assert r.status_code == 400


def test_update_menu_free_price_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], price=0), headers=headers)
    assert r.status_code == 200
    assert r.json()["price"] == 0


def test_update_menu_without_products(client, session):
    headers = admin_header(client, session)
    menu = create_menu(session, products=[create_product(session)])
    r = client.put(f"/menus/{menu.id}", json=menu_json([]), headers=headers)
    assert r.status_code == 400


# Dates : une seule date est autorisée
def test_update_menu_only_start_date_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], start_date="2026-11-16"), headers=headers)
    assert r.status_code == 200
    assert r.json()["start_date"] == "2026-11-16"
    assert r.json()["end_date"] is None


def test_update_menu_only_end_date_is_accepted(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(f"/menus/{menu.id}", json=menu_json([pizza.id], end_date="2026-11-22"), headers=headers)
    assert r.status_code == 200
    assert r.json()["start_date"] is None
    assert r.json()["end_date"] == "2026-11-22"


def test_update_menu_start_after_end(client, session):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(
        f"/menus/{menu.id}",
        json=menu_json([pizza.id], start_date="2026-11-22", end_date="2026-11-16"),
        headers=headers,
    )
    assert r.status_code == 400


@pytest.mark.parametrize("bad_date", ["pas-une-date", "25/12/2026", "2026-13-01", "2026-02-30", 20261225], ids=repr)
def test_update_menu_invalid_date_format(client, session, bad_date):
    headers = admin_header(client, session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    r = client.put(
        f"/menus/{menu.id}",
        json=menu_json([pizza.id], start_date=bad_date, end_date="2026-11-22"),
        headers=headers,
    )
    assert r.status_code == 422


def test_update_menu_missing_field(client, session):
    headers = admin_header(client, session)
    menu = create_menu(session, products=[create_product(session)])
    r = client.put(f"/menus/{menu.id}", json={"name": "Menu"}, headers=headers)
    assert r.status_code == 422