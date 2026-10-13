"""文件代理：从 MinIO 读取并返回，避免前端直连 MinIO。

object_key 中包含 UUID，外部无法猜测，因此无需额外鉴权
（与之前 MinIO presigned URL 的安全级别一致）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from ..core.config import get_settings
from ..core.minio_client import get_minio_client

logger = logging.getLogger(__name__)

router = APIRouter()

_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".svg": "image/svg+xml",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".mdj": "application/json",
}


@router.get("/files/{object_key:path}")
async def serve_file(object_key: str):
    """代理 MinIO 文件。object_key 含 UUID，不可猜测。"""
    settings = get_settings()
    try:
        client = get_minio_client()
        resp = client.get_object(settings.minio_bucket, object_key)
        data = resp.read()
        resp.close()
        resp.release_conn()
    except Exception as e:
        logger.warning("Failed to fetch %s from MinIO: %s", object_key, e)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文件不存在")

    ext = "." + object_key.rsplit(".", 1)[-1].lower() if "." in object_key else ""
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
