FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir ".[api,formats]"

EXPOSE 8000

ENV MAPPER_AUTH_DISABLED=true

CMD ["uvicorn", "erp_auto_mapper.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
