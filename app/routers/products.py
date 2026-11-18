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


def product_to_productOutput_type(product: Product):
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": product.price,
        "quantity": product.quantity,
        "is_available": product.is_available,
    }

def check_product_data_validity(product: ProductInput):

    if len(product.name) > 100 or not product.name.strip():
        raise HTTPException(status_code=400, detail="invalid name")

    if product.quantity < 0:
        raise HTTPException(status_code=400, detail="quantity must be >= 0")

    if product.price < 0.01:
        raise HTTPException(status_code=400, detail="price must be >= 0")



@router.get("", response_model = list[ProductOutput], summary="Lister tous les produits")
def get_all_products(session: Session = Depends(get_session)):
    products= session.exec(select(Product).where(Product.is_deleted == False)).all()

    return [
        product_to_productOutput_type(product)
        for product in products
    ]

@router.get("/{product_id}", response_model = ProductOutput, summary="Infos sur un produit")
def get_product_by_id(product_id: int, session: Session = Depends(get_session)):
    product:Product = session.exec(select(Product).where(Product.id == product_id)).first()

    if product is None or product.is_deleted:
        raise HTTPException(status_code=404, detail="product not found")

    return product_to_productOutput_type(product)




@router.post("", status_code=201, summary="Créer un produit")
def create_product(data: ProductInput, admin: User = Depends(require_admin), session: Session=Depends(get_session)):
    check_product_data_validity(data)

    product = Product(
        name = data.name.strip(),
        description=data.description,
        price=data.price,
        quantity=data.quantity,
        is_available=data.is_available,
    )

    session.add(product)
    session.commit()
    session.refresh(product)

    return product_to_productOutput_type(product)
