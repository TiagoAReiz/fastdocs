import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    PROJECT_NAME: str = "FastDocs"
    VERSION: str = "0.1.0"
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["*"]

    # Postgres
    DATABASE_URL: str = "postgresql+asyncpg://fastdocs:fastdocs@postgres:5432/fastdocs"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Azure Blob Storage
    AZURE_STORAGE_CONNECTION_STRING: str = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://azurite:10000/devstoreaccount1;"
    AZURE_STORAGE_CONTAINER: str = "documents"

    # Admin auth — service-to-service layer
    SERVICE_API_KEY: str = ""
    # IPs or CIDRs allowed to call /admin/* (e.g. ["10.0.0.5", "10.1.0.0/16"]).
    ADMIN_ALLOWED_IPS: Annotated[list[str], NoDecode] = []
    # IPs or CIDRs of reverse proxies whose X-Forwarded-For is trusted.
    # Empty (default) = X-Forwarded-For is ignored and the socket peer is used.
    TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []
    ENCRYPTION_KEY: str = ""  # Fernet key (urlsafe base64, 32 bytes)

    @field_validator("ADMIN_ALLOWED_IPS", "TRUSTED_PROXIES", mode="before")
    @classmethod
    def _parse_ip_list(cls, v: object) -> object:
        # Accepts a JSON list ('["10.0.0.1","10.1.0.0/16"]') or a comma-separated
        # string ("10.0.0.1, 10.1.0.0/16"). Entry validity is checked (fail closed)
        # in require_admin, so a typo denies admin access instead of crashing startup.
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):
                return json.loads(v)
            return [ip.strip() for ip in v.split(",") if ip.strip()]
        return v

    # Embedding
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIM: int = 768
    EMBEDDING_BATCH_SIZE: int = 50

    # Chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 150
    TABULAR_ROWS_PER_CHUNK: int = 20

    # OCR
    OCR_LANG: str = "por"
    OCR_DPI: int = 300
    SCANNED_PDF_CHAR_THRESHOLD: int = 100

    # Rate limiting
    RATE_LIMIT_INGEST: int = 50
    RATE_LIMIT_INGEST_WINDOW: int = 60
    RATE_LIMIT_QUERY: int = 200
    RATE_LIMIT_QUERY_WINDOW: int = 60

    # Outbox relay
    OUTBOX_RELAY_POLL_TIMEOUT: int = 20
    OUTBOX_RELAY_BATCH_SIZE: int = 50

    @property
    def DATABASE_URL_RAW(self) -> str:
        """DATABASE_URL stripped of the +asyncpg driver tag for use with asyncpg directly."""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
