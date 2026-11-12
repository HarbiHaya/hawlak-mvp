FROM python:3.12-slim AS build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock* ./
COPY src ./src
RUN uv sync --frozen --no-dev

FROM python:3.12-slim
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
EXPOSE 3100
CMD ["uvicorn", "hawlak_agent.web:create_app_from_env", "--factory", "--host", "0.0.0.0", "--port", "3100"]
