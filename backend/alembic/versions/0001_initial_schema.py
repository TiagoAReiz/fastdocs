"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

from app.core.config import settings


revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector extension — required before documents_embeddings table
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("hash_key", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_project", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("extraction_method", sa.String(20), nullable=True),
        sa.Column("extraction_notes", sa.Text, nullable=True),
        sa.Column("error_msg", sa.Text, nullable=True),
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )

    op.create_table(
        "documents_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_document", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("id_project", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", Vector(settings.EMBEDDING_DIM), nullable=True),
        sa.Column("chunk_index", sa.Integer, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "idx_embeddings_vec",
        "documents_embeddings",
        ["embedding"],
        postgresql_using="ivfflat",
        postgresql_with={"lists": 100},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "documents_metadata",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_document", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("metadata", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "chat_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_project", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "ix_chat_threads_tenant_project_updated",
        "chat_threads",
        ["id_tenant", "id_project", "updated_at"],
    )

    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("id_thread", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("chat_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_tenant", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_chat_messages_thread_created",
        "chat_messages",
        ["id_thread", "created_at"],
    )

    op.create_table(
        "outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("published", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # LISTEN/NOTIFY trigger for the outbox relay
    op.execute(
        """
        CREATE OR REPLACE FUNCTION notify_outbox() RETURNS trigger AS $$
        BEGIN
          PERFORM pg_notify('outbox_channel', '');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER outbox_notify AFTER INSERT ON outbox_events "
        "FOR EACH ROW EXECUTE FUNCTION notify_outbox()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS outbox_notify ON outbox_events")
    op.execute("DROP FUNCTION IF EXISTS notify_outbox()")

    op.drop_table("outbox_events")
    op.drop_index("ix_chat_messages_thread_created", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_index("ix_chat_threads_tenant_project_updated", table_name="chat_threads")
    op.drop_table("chat_threads")
    op.drop_table("documents_metadata")
    op.drop_index("idx_embeddings_vec", table_name="documents_embeddings")
    op.drop_table("documents_embeddings")
    op.drop_table("documents")
    op.drop_table("projects")
    op.drop_table("api_keys")
    op.drop_table("tenants")

    op.execute("DROP EXTENSION IF EXISTS vector")
