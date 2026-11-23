# tests/test_orders.py
import datetime as dt

import pytest
from sqlmodel import select

from app.models import ClosedDay, Menu, Order, OrderStatus, Product, User, UserRole
from app.security import create_token


# ---------- Fonctions utiles ----------
def create_user(session, username="alice", **options):
    # pas de vrai mot de passe : on fabrique le token directement (plus rapide que /auth/login)
    user = User(username=username, password_hash="x", **options)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def headers_of(user):
    return {"Authorization": f"Bearer {create_token(user.id)}"}


def create_admin(session):
    return create_user(session, username="admin", role=UserRole.ADMIN)


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


def pickup(days=3, hour=12):
    """Un instant futur, sous forme de texte JSON (heure locale, sans fuseau)."""
    day = dt.date.today() + dt.timedelta(days=days)
    return dt.datetime.combine(day, dt.time(hour, 0)).isoformat()


def pickup_day(days=3):
    return dt.date.today() + dt.timedelta(days=days)


def order_json(products=None, menus=None, when=None):
    return {
        "pickup_at": when or pickup(),
        "products": [{"product_id": p, "quantity": q} for p, q in (products or [])],
        "menus": [{"menu_id": m, "quantity": q} for m, q in (menus or [])],
    }


def place_order(client, user, products=None, menus=None, when=None):
    return client.post("/orders", json=order_json(products, menus, when), headers=headers_of(user))


def stock_of(session, product):
    session.expire_all()
    return session.get(Product, product.id).quantity


# =====================================================================
# POST /orders : passer une commande
# =====================================================================
def test_create_order_with_product(client, session):
    alice = create_user(session)
    pizza = create_product(session, price="8.50", quantity=10)

    r = place_order(client, alice, products=[(pizza.id, 2)])
    assert r.status_code == 201
    body = r.json()
    assert body["id"] is not None
    assert body["user_id"] == alice.id
    assert body["status"] == "pending"
    # la date est renvoyée en UTC ("Z") : on compare le même instant, pas le texte
    sent = dt.datetime.fromisoformat(pickup()).astimezone()
    assert dt.datetime.fromisoformat(body["pickup_at"]) == sent
    assert body["products"] == [{"product_id": pizza.id, "name": "Pizza", "quantity": 2, "unit_price": 8.5}]
    assert body["menus"] == []
    assert body["total"] == 17.0


def test_create_order_decrements_stock(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    place_order(client, alice, products=[(pizza.id, 3)])
    assert stock_of(session, pizza) == 7


def test_create_order_is_saved_in_database(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    place_order(client, alice, products=[(pizza.id, 1)])
    session.expire_all()
    orders = session.exec(select(Order)).all()
    assert len(orders) == 1
    assert orders[0].user_id == alice.id
    assert orders[0].status == OrderStatus.PENDING
    assert len(orders[0].product_lines) == 1


def test_create_order_with_menu(client, session):
    alice = create_user(session)
    menu = create_menu(session, products=[create_product(session)], price="12.00")
    r = place_order(client, alice, menus=[(menu.id, 2)])
    assert r.status_code == 201
    assert r.json()["menus"] == [{"menu_id": menu.id, "name": "Menu midi", "quantity": 2, "unit_price": 12.0}]
    assert r.json()["products"] == []
    assert r.json()["total"] == 24.0


def test_create_order_menu_does_not_change_product_stock(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    menu = create_menu(session, products=[pizza])
    place_order(client, alice, menus=[(menu.id, 2)])
    assert stock_of(session, pizza) == 10


def test_create_order_mixed_product_and_menu(client, session):
    alice = create_user(session)
    pizza = create_product(session, price="8.50")
    menu = create_menu(session, products=[pizza], price="12.00")
    r = place_order(client, alice, products=[(pizza.id, 1)], menus=[(menu.id, 1)])
    assert r.status_code == 201
    assert r.json()["total"] == 20.5


def test_create_order_without_menus_key(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    body = {"pickup_at": pickup(), "products": [{"product_id": pizza.id, "quantity": 1}]}
    r = client.post("/orders", json=body, headers=headers_of(alice))
    assert r.status_code == 201


def test_create_order_keeps_the_price_paid(client, session):
    alice = create_user(session)
    pizza = create_product(session, price="8.50")
    place_order(client, alice, products=[(pizza.id, 1)])

    # le prix change ensuite : la commande garde l'ancien prix
    session.expire_all()
    session.get(Product, pizza.id).price = "20.00"
    session.commit()

    r = client.get("/orders/me", headers=headers_of(alice))
    assert r.json()[0]["products"][0]["unit_price"] == 8.5
    assert r.json()[0]["total"] == 8.5


def test_create_order_ordering_all_the_stock(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=3)
    r = place_order(client, alice, products=[(pizza.id, 3)])
    assert r.status_code == 201
    assert stock_of(session, pizza) == 0


def test_create_order_with_timezone_in_pickup_at(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    day = dt.date.today() + dt.timedelta(days=5)
    when = f"{day.isoformat()}T12:00:00+00:00"
    r = place_order(client, alice, products=[(pizza.id, 1)], when=when)
    assert r.status_code == 201


def test_create_order_admin_can_order_too(client, session):
    admin = create_admin(session)
    pizza = create_product(session)
    assert place_order(client, admin, products=[(pizza.id, 1)]).status_code == 201


# ---------- accès ----------
def test_create_order_without_token(client, session):
    pizza = create_product(session)
    r = client.post("/orders", json=order_json(products=[(pizza.id, 1)]))
    assert r.status_code == 401


def test_create_order_blocked_user(client, session):
    alice = create_user(session, is_blocked=True)
    pizza = create_product(session)
    r = place_order(client, alice, products=[(pizza.id, 1)])
    assert r.status_code == 403
    assert stock_of(session, pizza) == 10


# ---------- données invalides ----------
def test_create_order_empty(client, session):
    alice = create_user(session)
    assert place_order(client, alice).status_code == 400


@pytest.mark.parametrize("quantity", [0, -1], ids=repr)
def test_create_order_invalid_quantity(client, session, quantity):
    alice = create_user(session)
    pizza = create_product(session)
    r = place_order(client, alice, products=[(pizza.id, quantity)])
    assert r.status_code == 400
    assert stock_of(session, pizza) == 10


def test_create_order_invalid_menu_quantity(client, session):
    alice = create_user(session)
    menu = create_menu(session, products=[create_product(session)])
    assert place_order(client, alice, menus=[(menu.id, 0)]).status_code == 400


def test_create_order_same_product_twice(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    r = place_order(client, alice, products=[(pizza.id, 1), (pizza.id, 2)])
    assert r.status_code == 400


def test_create_order_same_menu_twice(client, session):
    alice = create_user(session)
    menu = create_menu(session, products=[create_product(session)])
    assert place_order(client, alice, menus=[(menu.id, 1), (menu.id, 1)]).status_code == 400


def test_create_order_pickup_in_the_past(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    r = place_order(client, alice, products=[(pizza.id, 1)], when=pickup(days=-1))
    assert r.status_code == 400
    assert stock_of(session, pizza) == 10


def test_create_order_pickup_on_closed_day(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    session.add(ClosedDay(date=pickup_day(3), reason="Fermé"))
    session.commit()

    r = place_order(client, alice, products=[(pizza.id, 1)], when=pickup(days=3))
    assert r.status_code == 400
    assert stock_of(session, pizza) == 10


def test_create_order_other_day_than_closed_day_is_fine(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    session.add(ClosedDay(date=pickup_day(3), reason="Fermé"))
    session.commit()
    assert place_order(client, alice, products=[(pizza.id, 1)], when=pickup(days=4)).status_code == 201


@pytest.mark.parametrize("bad_date", ["pas-une-date", "25/12/2026", "2026-13-01T12:00:00", "", None, True], ids=repr)
def test_create_order_invalid_pickup_format(client, session, bad_date):
    alice = create_user(session)
    pizza = create_product(session)
    body = {"pickup_at": bad_date, "products": [{"product_id": pizza.id, "quantity": 1}], "menus": []}
    r = client.post("/orders", json=body, headers=headers_of(alice))
    assert r.status_code == 422


def test_create_order_missing_pickup(client, session):
    alice = create_user(session)
    r = client.post("/orders", json={"products": [], "menus": []}, headers=headers_of(alice))
    assert r.status_code == 422


# ---------- produits ----------
def test_create_order_unknown_product(client, session):
    alice = create_user(session)
    assert place_order(client, alice, products=[(9999, 1)]).status_code == 404


def test_create_order_deleted_product(client, session):
    alice = create_user(session)
    old = create_product(session, is_deleted=True)
    assert place_order(client, alice, products=[(old.id, 1)]).status_code == 404


def test_create_order_unavailable_product(client, session):
    alice = create_user(session)
    pizza = create_product(session, is_available=False)
    r = place_order(client, alice, products=[(pizza.id, 1)])
    assert r.status_code == 409
    assert stock_of(session, pizza) == 10


def test_create_order_not_enough_stock(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=2)
    r = place_order(client, alice, products=[(pizza.id, 3)])
    assert r.status_code == 409
    assert stock_of(session, pizza) == 2


def test_create_order_out_of_stock(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=0)
    assert place_order(client, alice, products=[(pizza.id, 1)]).status_code == 409


def test_create_order_stock_is_shared_between_orders(client, session):
    alice = create_user(session)
    bob = create_user(session, username="bob")
    pizza = create_product(session, quantity=5)
    assert place_order(client, alice, products=[(pizza.id, 3)]).status_code == 201
    assert place_order(client, bob, products=[(pizza.id, 3)]).status_code == 409   # il n'en reste que 2
    assert place_order(client, bob, products=[(pizza.id, 2)]).status_code == 201
    assert stock_of(session, pizza) == 0


# ---------- menus ----------
def test_create_order_unknown_menu(client, session):
    alice = create_user(session)
    assert place_order(client, alice, menus=[(9999, 1)]).status_code == 404


def test_create_order_deleted_menu(client, session):
    alice = create_user(session)
    menu = create_menu(session, products=[create_product(session)], is_deleted=True)
    assert place_order(client, alice, menus=[(menu.id, 1)]).status_code == 404


def test_create_order_disabled_menu(client, session):
    alice = create_user(session)
    menu = create_menu(session, products=[create_product(session)], is_available=False)
    assert place_order(client, alice, menus=[(menu.id, 1)]).status_code == 400


def test_create_order_menu_available_on_pickup_day(client, session):
    alice = create_user(session)
    menu = create_menu(
        session, products=[create_product(session)],
        start_date=pickup_day(3), end_date=pickup_day(3),
    )
    assert place_order(client, alice, menus=[(menu.id, 1)], when=pickup(days=3)).status_code == 201


def test_create_order_menu_not_available_on_pickup_day(client, session):
    alice = create_user(session)
    menu = create_menu(
        session, products=[create_product(session)],
        start_date=pickup_day(3), end_date=pickup_day(3),
    )
    assert place_order(client, alice, menus=[(menu.id, 1)], when=pickup(days=4)).status_code == 400
    assert place_order(client, alice, menus=[(menu.id, 1)], when=pickup(days=2)).status_code == 400


# ---------- tout ou rien ----------
def test_create_order_error_saves_nothing(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    # le produit est valide, mais le menu n'existe pas : rien ne doit être modifié
    r = place_order(client, alice, products=[(pizza.id, 2)], menus=[(9999, 1)])
    assert r.status_code == 404
    assert stock_of(session, pizza) == 10
    assert session.exec(select(Order)).all() == []


def test_create_order_second_product_out_of_stock_saves_nothing(client, session):
    alice = create_user(session)
    pizza = create_product(session, name="Pizza", quantity=10)
    salade = create_product(session, name="Salade", quantity=1)
    r = place_order(client, alice, products=[(pizza.id, 2), (salade.id, 5)])
    assert r.status_code == 409
    assert stock_of(session, pizza) == 10     # la pizza, pourtant valide, n'a pas été décrémentée
    assert stock_of(session, salade) == 1
    assert session.exec(select(Order)).all() == []


# =====================================================================
# GET /orders/me : mes commandes
# =====================================================================
def test_my_orders_only_mine(client, session):
    alice = create_user(session)
    bob = create_user(session, username="bob")
    pizza = create_product(session)
    place_order(client, alice, products=[(pizza.id, 1)])
    place_order(client, bob, products=[(pizza.id, 1)])

    r = client.get("/orders/me", headers=headers_of(alice))
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["user_id"] == alice.id


def test_my_orders_empty(client, session):
    alice = create_user(session)
    r = client.get("/orders/me", headers=headers_of(alice))
    assert r.status_code == 200
    assert r.json() == []


def test_my_orders_newest_first(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    first = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    second = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    ids = [o["id"] for o in client.get("/orders/me", headers=headers_of(alice)).json()]
    assert ids == [second, first]


def test_my_orders_contain_their_lines(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    menu = create_menu(session, products=[pizza])
    place_order(client, alice, products=[(pizza.id, 2)], menus=[(menu.id, 1)])
    order = client.get("/orders/me", headers=headers_of(alice)).json()[0]
    assert len(order["products"]) == 1
    assert len(order["menus"]) == 1


def test_my_orders_without_token(client):
    assert client.get("/orders/me").status_code == 401


# =====================================================================
# PATCH /orders/{id}/cancel : annuler ma commande
# =====================================================================
def test_cancel_order_ok(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    order_id = place_order(client, alice, products=[(pizza.id, 3)]).json()["id"]
    assert stock_of(session, pizza) == 7

    r = client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice))
    assert r.status_code == 200
    assert r.json() == {"id": order_id, "status": "cancelled"}
    assert stock_of(session, pizza) == 10      # le stock est rendu


def test_cancel_order_restores_stock_of_every_line(client, session):
    alice = create_user(session)
    pizza = create_product(session, name="Pizza", quantity=10)
    salade = create_product(session, name="Salade", quantity=5)
    order_id = place_order(client, alice, products=[(pizza.id, 2), (salade.id, 4)]).json()["id"]
    client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice))
    assert stock_of(session, pizza) == 10
    assert stock_of(session, salade) == 5


def test_cancel_order_restores_stock_even_if_product_deleted_since(client, session):
    alice = create_user(session)
    admin = create_admin(session)
    pizza = create_product(session, quantity=10)
    order_id = place_order(client, alice, products=[(pizza.id, 3)]).json()["id"]
    client.delete(f"/products/{pizza.id}", headers=headers_of(admin))

    assert client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice)).status_code == 200


def test_cancel_order_then_visible_as_cancelled(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    order_id = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice))
    assert client.get("/orders/me", headers=headers_of(alice)).json()[0]["status"] == "cancelled"


def test_cancel_order_twice(client, session):
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    order_id = place_order(client, alice, products=[(pizza.id, 3)]).json()["id"]
    client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice))
    r = client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice))
    assert r.status_code == 409
    assert stock_of(session, pizza) == 10      # le stock n'est pas rendu deux fois


@pytest.mark.parametrize("status", [OrderStatus.READY, OrderStatus.PICKED_UP, OrderStatus.NOT_HONORED], ids=repr)
def test_cancel_order_not_pending(client, session, status):
    alice = create_user(session)
    pizza = create_product(session)
    order_id = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    session.expire_all()
    session.get(Order, order_id).status = status
    session.commit()
    assert client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice)).status_code == 409


def test_cancel_someone_elses_order(client, session):
    alice = create_user(session)
    bob = create_user(session, username="bob")
    pizza = create_product(session, quantity=10)
    order_id = place_order(client, alice, products=[(pizza.id, 3)]).json()["id"]

    r = client.patch(f"/orders/{order_id}/cancel", headers=headers_of(bob))
    assert r.status_code == 403
    assert stock_of(session, pizza) == 7


def test_cancel_order_unknown(client, session):
    alice = create_user(session)
    assert client.patch("/orders/9999/cancel", headers=headers_of(alice)).status_code == 404


def test_cancel_order_without_token(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    order_id = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    assert client.patch(f"/orders/{order_id}/cancel").status_code == 401


# =====================================================================
# GET /orders : toutes les commandes (admin)
# =====================================================================
def test_list_all_orders_as_admin(client, session):
    admin = create_admin(session)
    alice = create_user(session)
    bob = create_user(session, username="bob")
    pizza = create_product(session)
    place_order(client, alice, products=[(pizza.id, 1)])
    place_order(client, bob, products=[(pizza.id, 1)])

    r = client.get("/orders", headers=headers_of(admin))
    assert r.status_code == 200
    assert sorted(o["user_id"] for o in r.json()) == sorted([alice.id, bob.id])


def test_list_all_orders_sorted_by_pickup(client, session):
    admin = create_admin(session)
    alice = create_user(session)
    pizza = create_product(session)
    late = place_order(client, alice, products=[(pizza.id, 1)], when=pickup(days=6)).json()["id"]
    early = place_order(client, alice, products=[(pizza.id, 1)], when=pickup(days=2)).json()["id"]
    ids = [o["id"] for o in client.get("/orders", headers=headers_of(admin)).json()]
    assert ids == [early, late]


def test_list_all_orders_filter_by_status(client, session):
    admin = create_admin(session)
    alice = create_user(session)
    pizza = create_product(session)
    keep = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    cancelled = place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]
    client.patch(f"/orders/{cancelled}/cancel", headers=headers_of(alice))

    pending = client.get("/orders", params={"status": "pending"}, headers=headers_of(admin)).json()
    assert [o["id"] for o in pending] == [keep]
    only_cancelled = client.get("/orders", params={"status": "cancelled"}, headers=headers_of(admin)).json()
    assert [o["id"] for o in only_cancelled] == [cancelled]


def test_list_all_orders_filter_without_result(client, session):
    admin = create_admin(session)
    r = client.get("/orders", params={"status": "picked_up"}, headers=headers_of(admin))
    assert r.status_code == 200
    assert r.json() == []


def test_list_all_orders_invalid_status(client, session):
    admin = create_admin(session)
    r = client.get("/orders", params={"status": "n_importe_quoi"}, headers=headers_of(admin))
    assert r.status_code == 422


def test_list_all_orders_forbidden_for_standard_user(client, session):
    alice = create_user(session)
    assert client.get("/orders", headers=headers_of(alice)).status_code == 403


def test_list_all_orders_without_token(client):
    assert client.get("/orders").status_code == 401


# =====================================================================
# PATCH /orders/{id}/status : changer le statut (admin)
# =====================================================================
def make_pending_order(client, session):
    alice = create_user(session)
    pizza = create_product(session)
    return place_order(client, alice, products=[(pizza.id, 1)]).json()["id"]


@pytest.mark.parametrize("new_status", ["ready", "picked_up", "not_honored"])
def test_change_status_from_pending(client, session, new_status):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    r = client.patch(f"/orders/{order_id}/status", json={"status": new_status}, headers=headers_of(admin))
    assert r.status_code == 200
    assert r.json() == {"id": order_id, "status": new_status}

    session.expire_all()
    assert session.get(Order, order_id).status == new_status


def test_change_status_ready_then_picked_up(client, session):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    client.patch(f"/orders/{order_id}/status", json={"status": "ready"}, headers=headers_of(admin))
    r = client.patch(f"/orders/{order_id}/status", json={"status": "picked_up"}, headers=headers_of(admin))
    assert r.status_code == 200


def test_change_status_ready_then_not_honored(client, session):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    client.patch(f"/orders/{order_id}/status", json={"status": "ready"}, headers=headers_of(admin))
    r = client.patch(f"/orders/{order_id}/status", json={"status": "not_honored"}, headers=headers_of(admin))
    assert r.status_code == 200


@pytest.mark.parametrize("new_status", ["pending", "ready", "picked_up", "not_honored", "cancelled"])
@pytest.mark.parametrize("old_status", ["pending", "ready", "picked_up", "not_honored", "cancelled"])
def test_change_status_any_to_any(client, session, old_status, new_status):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    client.patch(f"/orders/{order_id}/status", json={"status": old_status}, headers=headers_of(admin))
    r = client.patch(f"/orders/{order_id}/status", json={"status": new_status}, headers=headers_of(admin))
    assert r.status_code == 200
    assert r.json() == {"id": order_id, "status": new_status}


# ---- le stock suit les changements de statut ----
def order_of_3_pizzas(client, session):
    """Stock de départ 10, commande de 3 : il reste 7."""
    admin = create_admin(session)
    alice = create_user(session)
    pizza = create_product(session, quantity=10)
    order_id = place_order(client, alice, products=[(pizza.id, 3)]).json()["id"]
    return admin, pizza, order_id


def set_status(client, admin, order_id, status):
    return client.patch(f"/orders/{order_id}/status", json={"status": status}, headers=headers_of(admin))


def test_change_status_to_cancelled_gives_stock_back(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    assert stock_of(session, pizza) == 7
    assert set_status(client, admin, order_id, "cancelled").status_code == 200
    assert stock_of(session, pizza) == 10


@pytest.mark.parametrize("status", ["ready", "picked_up", "not_honored"])
def test_change_status_to_cancelled_from_any_status_gives_stock_back(client, session, status):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, status)
    set_status(client, admin, order_id, "cancelled")
    assert stock_of(session, pizza) == 10


@pytest.mark.parametrize("status", ["pending", "ready", "picked_up", "not_honored"])
def test_change_status_without_cancelling_keeps_stock(client, session, status):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, status)
    assert stock_of(session, pizza) == 7


def test_not_honored_keeps_stock_taken(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "not_honored")
    assert stock_of(session, pizza) == 7     # les produits préparés sont perdus


@pytest.mark.parametrize("status", ["pending", "ready", "picked_up", "not_honored"])
def test_reactivating_a_cancelled_order_takes_stock_again(client, session, status):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "cancelled")
    assert stock_of(session, pizza) == 10
    assert set_status(client, admin, order_id, status).status_code == 200
    assert stock_of(session, pizza) == 7


def test_reactivating_a_cancelled_order_without_enough_stock(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "cancelled")
    # entre-temps, quelqu'un d'autre commande presque tout le stock
    bob = create_user(session, username="bob")
    assert place_order(client, bob, products=[(pizza.id, 9)]).status_code == 201
    assert stock_of(session, pizza) == 1

    r = set_status(client, admin, order_id, "ready")
    assert r.status_code == 409
    assert stock_of(session, pizza) == 1                 # rien n'a changé
    session.expire_all()
    assert session.get(Order, order_id).status == OrderStatus.CANCELLED


def test_reactivating_does_not_change_stock_if_one_product_is_missing(client, session):
    admin = create_admin(session)
    alice = create_user(session)
    pizza = create_product(session, name="Pizza", quantity=10)
    salade = create_product(session, name="Salade", quantity=5)
    order_id = place_order(client, alice, products=[(pizza.id, 2), (salade.id, 5)]).json()["id"]
    set_status(client, admin, order_id, "cancelled")
    bob = create_user(session, username="bob")
    place_order(client, bob, products=[(salade.id, 4)])      # il reste 1 salade

    assert set_status(client, admin, order_id, "pending").status_code == 409
    assert stock_of(session, pizza) == 10                    # la pizza n'a pas été retirée non plus


def test_cancelled_twice_gives_stock_back_only_once(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "cancelled")
    set_status(client, admin, order_id, "cancelled")
    assert stock_of(session, pizza) == 10


def test_same_status_does_not_change_stock(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "pending")
    assert stock_of(session, pizza) == 7


def test_client_cannot_cancel_an_order_cancelled_by_admin(client, session):
    admin, pizza, order_id = order_of_3_pizzas(client, session)
    set_status(client, admin, order_id, "cancelled")
    alice = session.exec(select(User).where(User.username == "alice")).one()
    assert client.patch(f"/orders/{order_id}/cancel", headers=headers_of(alice)).status_code == 409
    assert stock_of(session, pizza) == 10


def test_change_status_invalid_value(client, session):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    r = client.patch(f"/orders/{order_id}/status", json={"status": "n_importe_quoi"}, headers=headers_of(admin))
    assert r.status_code == 422


def test_change_status_missing_field(client, session):
    admin = create_admin(session)
    order_id = make_pending_order(client, session)
    assert client.patch(f"/orders/{order_id}/status", json={}, headers=headers_of(admin)).status_code == 422


def test_change_status_unknown_order(client, session):
    admin = create_admin(session)
    r = client.patch("/orders/9999/status", json={"status": "ready"}, headers=headers_of(admin))
    assert r.status_code == 404


def test_change_status_forbidden_for_standard_user(client, session):
    alice = create_user(session, username="other")
    order_id = make_pending_order(client, session)
    r = client.patch(f"/orders/{order_id}/status", json={"status": "ready"}, headers=headers_of(alice))
    assert r.status_code == 403


def test_change_status_without_token(client, session):
    order_id = make_pending_order(client, session)
    assert client.patch(f"/orders/{order_id}/status", json={"status": "ready"}).status_code == 401