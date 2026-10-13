"""MinIO 对象存储客户端。"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from .config import get_settings

logger = logging.getLogger(__name__)

_client: Minio | None = None


_bucket_ensured = False


def get_minio_client() -> Minio:
    """进程内单例 MinIO 客户端。"""
    global _client, _bucket_ensured
    if _client is None:
        settings = get_settings()
        _client = Minio(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
    # 确保 bucket 存在（只尝试一次成功即可）
    if not _bucket_ensured:
        try:
            bucket = get_settings().minio_bucket
            if not _client.bucket_exists(bucket):
                _client.make_bucket(bucket)
                logger.info("Created MinIO bucket: %s", bucket)
            _bucket_ensured = True
        except Exception as e:
            logger.warning("MinIO bucket check failed: %s", e)
            raise
    return _client


def _save_local_fallback(data: bytes, object_name: str) -> str:
    """MinIO 不可用时回退到本地 uploads/ 目录。"""
    settings = get_settings()
    dest = settings.uploads_dir / object_name.replace("/", "_")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    logger.info("Saved locally (MinIO unavailable): %s (%d bytes)", dest, len(data))
    return object_name


def upload_file_to_minio(
    data: bytes,
    *,
    original_filename: str = "",
    prefix: str = "uploads",
    content_type: str = "application/octet-stream",
) -> str:
    """上传文件到 MinIO，返回对象 key（路径）。MinIO 不可用时回退到本地存储。"""
    ext = Path(original_filename).suffix.lower() if original_filename else ""
    object_name = f"{prefix}/{uuid.uuid4().hex}{ext}"
    try:
        settings = get_settings()
        client = get_minio_client()
        client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=object_name,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        logger.info("Uploaded to MinIO: %s (%d bytes)", object_name, len(data))
    except Exception as e:
        logger.warning("MinIO upload failed, falling back to local: %s", e)
        _save_local_fallback(data, object_name)
    return object_name


def get_minio_url(object_name: str, expires_hours: int = 24) -> str | None:
    """返回后端代理 URL，供前端直接用作 <img src>。

    不再使用 MinIO presigned URL（因为 MinIO endpoint 通常是
    localhost:9000，外部浏览器无法访问），改为通过 /api/files/ 代理。
    """
    from urllib.parse import quote
    return f"/api/files/{quote(object_name, safe='/')}"


def delete_from_minio(object_name: str) -> None:
    """从 MinIO 删除对象。"""
    settings = get_settings()
    client = get_minio_client()
    try:
        client.remove_object(settings.minio_bucket, object_name)
    except S3Error as e:
        logger.warning("Failed to delete %s from MinIO: %s", object_name, e)
