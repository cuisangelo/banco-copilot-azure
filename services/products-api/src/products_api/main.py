import hmac
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter

from bank_contracts.models import Product, ProductCategory
from bank_contracts.settings import require_env


def create_app() -> FastAPI:
    backend_secret = require_env("BACKEND_SECRET")
    products = TypeAdapter(list[Product]).validate_python(
        json.loads(Path(require_env("PRODUCTS_PATH")).read_text())
    )
    by_id = {p.id: p for p in products}

    app = FastAPI(title="products-api")

    @app.middleware("http")
    async def require_backend_secret(request: Request, call_next):
        received = request.headers.get("X-Backend-Secret", "")
        if not hmac.compare_digest(received.encode(), backend_secret.encode()):
            return JSONResponse({"detail": "missing or invalid backend secret"}, status_code=401)
        return await call_next(request)

    @app.get("/products")
    def list_products(category: ProductCategory | None = None) -> list[Product]:
        return [p for p in products if category is None or p.category == category]

    @app.get("/products/{product_id}")
    def get_product(product_id: str) -> Product:
        if product_id not in by_id:
            raise HTTPException(404, "product not found")
        return by_id[product_id]

    return app
