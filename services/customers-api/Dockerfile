# Build from the repo root: docker build -f services/customers-api/Dockerfile .
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/contracts packages/contracts
COPY services/customers-api services/customers-api
RUN uv sync --frozen --no-dev --package customers-api
COPY data/customers.json data/customers.json
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "customers_api.main:app_from_env", "--factory", "--host", "0.0.0.0", "--port", "8000"]
