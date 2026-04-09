import uuid as uuid_mod
from uuid import UUID

from app.core.storage import get_container_client


def generate_file_path(tenant_id: UUID, project_id: UUID, filename: str) -> str:
    unique = uuid_mod.uuid4().hex[:12]
    return f"{tenant_id}/{project_id}/{unique}_{filename}"


def upload_file(file_path: str, content: bytes, content_type: str) -> str:
    container = get_container_client()
    blob = container.get_blob_client(file_path)
    blob.upload_blob(content, content_type=content_type, overwrite=True)
    return file_path


def download_file(file_path: str) -> bytes:
    container = get_container_client()
    blob = container.get_blob_client(file_path)
    return blob.download_blob().readall()


def delete_file(file_path: str) -> None:
    container = get_container_client()
    blob = container.get_blob_client(file_path)
    blob.delete_blob()
