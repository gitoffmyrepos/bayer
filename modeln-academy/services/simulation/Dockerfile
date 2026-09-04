FROM ghcr.io/astral-sh/uv:0.10.11 AS uv

FROM python:3.13-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
COPY shared/python ./shared/python
COPY services ./services
COPY content/dist/course-v1.json ./content/course-v1.json
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONPATH="/app/shared/python:/app"
USER 10001:10001
EXPOSE 8080
CMD ["uvicorn", "services.simulation.app.main:default_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
