from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.database import get_db
from app.models.user import User
from app.models.restaurant import Restaurant
from app.models.menu_category import MenuCategory
from app.models.menu_item import MenuItem
from app.schemas.restaurant import (
    RestaurantCreate,
    RestaurantUpdate,
    RestaurantResponse,
    OpenStatusUpdate,
)
from app.schemas.menu import (
    CategoryCreate,
    CategoryResponse,
    MenuItemCreate,
    MenuItemUpdate,
    MenuItemResponse,
    AvailabilityUpdate,
)

router = APIRouter(tags=["Restaurants & Menu"])


def require_approved_owner(user: User) -> None:
    if user.role != "Restaurant Owner":
        raise HTTPException(
            status_code=403,
            detail="Only Restaurant Owners can perform this action",
        )

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive")

    if not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Admin approval is required",
        )


def get_owned_restaurant(
    restaurant_id: int,
    user: User,
    db: Session,
) -> Restaurant:
    restaurant = db.get(Restaurant, restaurant_id)

    if restaurant is None:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    if restaurant.owner_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot manage another owner's restaurant",
        )

    return restaurant


# ---------------- RESTAURANT APIs ----------------

@router.post(
    "/restaurants",
    response_model=RestaurantResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_restaurant(
    data: RestaurantCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)

    restaurant = Restaurant(
        **data.model_dump(),
        owner_id=user.id,
        is_temporarily_closed=False,
        average_rating=0,
        is_active=True,
    )

    db.add(restaurant)
    db.commit()
    db.refresh(restaurant)

    return restaurant


@router.get("/restaurants/me", response_model=list[RestaurantResponse])
def get_my_restaurants(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)

    return (
        db.query(Restaurant)
        .filter(Restaurant.owner_id == user.id)
        .order_by(Restaurant.id.desc())
        .all()
    )


@router.get(
    "/restaurants/{restaurant_id}",
    response_model=RestaurantResponse,
)
def get_restaurant(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)

    if restaurant is None or not restaurant.is_active:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    return restaurant


@router.put(
    "/restaurants/{restaurant_id}",
    response_model=RestaurantResponse,
)
def update_restaurant(
    restaurant_id: int,
    data: RestaurantUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)
    restaurant = get_owned_restaurant(restaurant_id, user, db)

    changes = data.model_dump(exclude_unset=True)

    for field, value in changes.items():
        setattr(restaurant, field, value)

    restaurant.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(restaurant)

    return restaurant


@router.put(
    "/restaurants/{restaurant_id}/open-status",
    response_model=RestaurantResponse,
)
def update_open_status(
    restaurant_id: int,
    data: OpenStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)
    restaurant = get_owned_restaurant(restaurant_id, user, db)

    restaurant.is_temporarily_closed = data.is_temporarily_closed
    restaurant.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(restaurant)

    return restaurant


# ---------------- CATEGORY API ----------------

@router.post(
    "/restaurants/{restaurant_id}/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    restaurant_id: int,
    data: CategoryCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)
    restaurant = get_owned_restaurant(restaurant_id, user, db)

    if not restaurant.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot add categories to an inactive restaurant",
        )

    category = MenuCategory(
        restaurant_id=restaurant.id,
        name=data.name.strip(),
    )

    db.add(category)

    try:
        db.commit()
        db.refresh(category)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="This category already exists for the restaurant",
        )

    return category


# ---------------- MENU ITEM APIs ----------------

@router.post(
    "/restaurants/{restaurant_id}/menu-items",
    response_model=MenuItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_menu_item(
    restaurant_id: int,
    data: MenuItemCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)
    restaurant = get_owned_restaurant(restaurant_id, user, db)

    if not restaurant.is_active:
        raise HTTPException(
            status_code=400,
            detail="Cannot add items to an inactive restaurant",
        )

    category = db.get(MenuCategory, data.category_id)

    if (
        category is None
        or category.restaurant_id != restaurant.id
        or not category.is_active
    ):
        raise HTTPException(
            status_code=400,
            detail="Choose an active category belonging to this restaurant",
        )

    item = MenuItem(
        restaurant_id=restaurant.id,
        **data.model_dump(),
        is_available=True,
        is_deleted=False,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return item


@router.get(
    "/restaurants/{restaurant_id}/menu",
)
def get_restaurant_menu(
    restaurant_id: int,
    db: Session = Depends(get_db),
):
    restaurant = db.get(Restaurant, restaurant_id)

    if restaurant is None or not restaurant.is_active:
        raise HTTPException(status_code=404, detail="Restaurant not found")

    categories = (
        db.query(MenuCategory)
        .filter(
            MenuCategory.restaurant_id == restaurant_id,
            MenuCategory.is_active.is_(True),
        )
        .order_by(MenuCategory.name)
        .all()
    )

    grouped_menu = []

    for category in categories:
        items = (
            db.query(MenuItem)
            .filter(
                MenuItem.restaurant_id == restaurant_id,
                MenuItem.category_id == category.id,
                MenuItem.is_deleted.is_(False),
            )
            .order_by(MenuItem.name)
            .all()
        )

        grouped_menu.append({
            "category_id": category.id,
            "category_name": category.name,
            "items": [
                {
                    "id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "price": item.price,
                    "is_veg": item.is_veg,
                    "packaging_charge": item.packaging_charge,
                    "is_available": item.is_available,
                }
                for item in items
            ],
        })

    return {
        "restaurant_id": restaurant.id,
        "restaurant_name": restaurant.name,
        "is_open": restaurant.is_open,
        "categories": grouped_menu,
    }


@router.put(
    "/menu-items/{item_id}",
    response_model=MenuItemResponse,
)
def update_menu_item(
    item_id: int,
    data: MenuItemUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)

    item = db.get(MenuItem, item_id)

    if item is None or item.is_deleted:
        raise HTTPException(status_code=404, detail="Menu item not found")

    get_owned_restaurant(item.restaurant_id, user, db)

    changes = data.model_dump(exclude_unset=True)

    if "category_id" in changes:
        category = db.get(MenuCategory, changes["category_id"])

        if (
            category is None
            or category.restaurant_id != item.restaurant_id
            or not category.is_active
        ):
            raise HTTPException(
                status_code=400,
                detail="Category must belong to this restaurant",
            )

    for field, value in changes.items():
        setattr(item, field, value)

    item.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    return item


@router.put(
    "/menu-items/{item_id}/availability",
    response_model=MenuItemResponse,
)
def update_menu_item_availability(
    item_id: int,
    data: AvailabilityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)

    item = db.get(MenuItem, item_id)

    if item is None or item.is_deleted:
        raise HTTPException(status_code=404, detail="Menu item not found")

    get_owned_restaurant(item.restaurant_id, user, db)

    item.is_available = data.is_available
    item.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(item)

    return item


@router.delete(
    "/menu-items/{item_id}",
    status_code=status.HTTP_200_OK,
)
def delete_menu_item(
    item_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    require_approved_owner(user)

    item = db.get(MenuItem, item_id)

    if item is None or item.is_deleted:
        raise HTTPException(status_code=404, detail="Menu item not found")

    get_owned_restaurant(item.restaurant_id, user, db)

    # Soft delete: preserve the record for historical orders.
    item.is_deleted = True
    item.is_available = False
    item.deleted_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()

    db.commit()

    return {"message": "Menu item deleted successfully"}