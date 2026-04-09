from azure.storage.blob import BlobServiceClient

from app.core.config import settings

blob_service_client = BlobServiceClient.from_connection_string(
    settings.AZURE_STORAGE_CONNECTION_STRING
)


def get_container_client():
    container = blob_service_client.get_container_client(settings.AZURE_STORAGE_CONTAINER)
    if not container.exists():
        container.create_container()
    return container
