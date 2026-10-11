# Build from the repo root: docker build -f services/products-api/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/contracts packages/contracts
COPY services/products-api services/products-api
RUN uv sync --frozen --no-dev --package products-api
COPY data/products.json data/products.json
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "products_api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
