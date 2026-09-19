"""Put the Telegram processing claim on inbound updates."""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("telegram_updates", sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True))
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("telegram_links", recreate="always") as batch:
            batch.drop_column("processing_at")
    else:
        op.drop_column("telegram_links", "processing_at")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("telegram_links", recreate="always") as batch:
            batch.add_column(sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True))
    else:
        op.add_column("telegram_links", sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_column("telegram_updates", "processing_at")
