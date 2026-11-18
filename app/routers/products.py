from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from dataclasses import dataclass
from app.database import get_session
from app.models import User, Product
from app.security import get_current_user, verify_password, require_admin

router = APIRouter(prefix="/products", tags=["products"])

@dataclass
class ProductInput:
    name: str
    description: str | None
    price: float
    quantity: int
    is_available: bool


@dataclass
class ProductOutput:
    id: int
    name: str
    description: str | None
    price: float
    quantity: int
    is_available: bool



@router.get("", response_model = list[ProductOutput], summary="Lister tous les produits")
def get_all_products(session: Session = Depends(get_session)):
    products= session.exec(select(Product).where(Product.is_deleted == False)).all()

    return [
        {
            "id": product.id,
            "name": product.name,
            "description": product.description,
            "price": product.price,
            "quantity": product.quantity,
            "is_available": product.is_available,
        }
        for product in products
    ]

@router.get("/{product_id}", response_model = ProductOutput, summary="Infos sur un produit")
def get_product_by_id(product_id: int, session: Session = Depends(get_session)):
    product:Product = session.exec(select(Product).where(Product.id == product_id)).first()

    if product is None or product.is_deleted:
        raise HTTPException(status_code=404, detail="product not found")

    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "quantity": product.quantity,
        "is_available": product.is_available,
    }