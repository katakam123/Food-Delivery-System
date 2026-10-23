from fastapi import FastAPI

from app.routers.auth import router as auth_router
from app.routers.admin import router as admin_router
from app.routers.restaurants import router as restaurants_router
from app.routers.addresses import router as addresses_router
from app.routers.cart import router as cart_router
from app.routers.coupons import router as coupons_router
from app.routers.orders import router as orders_router
from app.routers.restaurant_orders import (
    router as restaurant_orders_router,
)
from app.routers.delivery import router as delivery_router
from app.routers.websockets import router as websockets_router
from pathlib import Path
from app.jobs.scheduled_jobs import start_scheduler, stop_scheduler
from app.routers.ratings import router as ratings_router
from fastapi.responses import FileResponse
from app.routers.reports import router as reports_router
app = FastAPI(
    title="Food Delivery System API",
    version="1.0.0",
)

@app.get("/tracking")
def get_tracking_test():
    return FileResponse(Path("static/tracking_test.html"))

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(restaurants_router)
app.include_router(addresses_router)
app.include_router(cart_router)
app.include_router(coupons_router)
app.include_router(orders_router)
app.include_router(restaurant_orders_router)
app.include_router(delivery_router)
app.include_router(websockets_router)   
app.include_router(ratings_router)
app.include_router(reports_router)

@app.get("/")
def root():
    return {"message": "Food Delivery System API"}


@app.get("/health")
def health():
    return {"status": "healthy"}