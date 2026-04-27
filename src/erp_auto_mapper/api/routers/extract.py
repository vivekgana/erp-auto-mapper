"""POST /v1/extract — upload file and infer schema."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Request, UploadFile

from erp_auto_mapper.api.auth import get_current_user
from erp_auto_mapper.core.ingest.file_reader import FileFormatReader
from erp_auto_mapper.core.ingest.schema_inferrer import SchemaInferrer

router = APIRouter(prefix="/v1", tags=["extract"])


@router.post("/extract")
async def extract_schema(
    request: Request,
    file: UploadFile = File(...),
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    rate_limiter = request.app.state.rate_limiter
    tenant_id = user.get("tenant_id", user.get("sub", "anonymous"))
    rate_limiter.check_request_count(tenant_id)

    content = await file.read()
    suffix = Path(file.filename or "data.csv").suffix

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        reader = FileFormatReader()
        read_result = reader.read(tmp_path)

        inferrer = SchemaInferrer()
        inferred_fields = inferrer.infer_fields(read_result.rows)

        return {
            "filename": file.filename,
            "rows": read_result.row_count,
            "fields": [
                {"name": f.name, "type": f.type, "nullable": getattr(f, "nullable", True)}
                for f in inferred_fields
            ],
        }
    finally:
        tmp_path.unlink(missing_ok=True)
