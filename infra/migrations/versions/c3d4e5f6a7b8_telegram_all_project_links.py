"""Allow one configured Telegram chat to link every project."""

from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        with op.batch_alter_table("telegram_links", recreate="always") as batch:
            batch.drop_constraint("uq_telegram_link_chat", type_="unique")
            batch.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
            batch.create_unique_constraint("uq_telegram_link_chat_project", ["chat_id", "project_id"])
            batch.alter_column("is_active", server_default=None)
        with op.batch_alter_table("telegram_outbox", recreate="always") as batch:
            batch.add_column(sa.Column("reply_markup", sa.JSON(), nullable=True))
    else:
        op.drop_constraint("uq_telegram_link_chat", "telegram_links", type_="unique")
        op.add_column("telegram_links", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.alter_column("telegram_links", "is_active", server_default=None)
        op.create_unique_constraint("uq_telegram_link_chat_project", "telegram_links", ["chat_id", "project_id"])
        op.add_column("telegram_outbox", sa.Column("reply_markup", sa.JSON(), nullable=True))
    op.create_index(
        "uq_telegram_link_active_chat",
        "telegram_links",
        ["chat_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
        sqlite_where=sa.text("is_active = 1"),
    )


def downgrade() -> None:
    op.drop_index("uq_telegram_link_active_chat", table_name="telegram_links")
    op.drop_column("telegram_outbox", "reply_markup")
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("telegram_links", recreate="always") as batch:
            batch.drop_constraint("uq_telegram_link_chat_project", type_="unique")
            batch.drop_column("is_active")
            batch.create_unique_constraint("uq_telegram_link_chat", ["chat_id"])
    else:
        op.drop_constraint("uq_telegram_link_chat_project", "telegram_links", type_="unique")
        op.drop_column("telegram_links", "is_active")
        op.create_unique_constraint("uq_telegram_link_chat", "telegram_links", ["chat_id"])
