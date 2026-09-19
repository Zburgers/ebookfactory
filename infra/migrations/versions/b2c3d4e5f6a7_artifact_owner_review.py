"""Persist owner review decisions for generated artifacts."""

from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("artifacts", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("owner_review_state", sa.String(length=32), nullable=False, server_default="pending"))
            batch_op.add_column(sa.Column("owner_review_note", sa.Text(), nullable=True))
            batch_op.add_column(sa.Column("owner_reviewed_at", sa.DateTime(timezone=True), nullable=True))
            batch_op.alter_column("owner_review_state", server_default=None)
    else:
        op.add_column("artifacts", sa.Column("owner_review_state", sa.String(length=32), nullable=False, server_default="pending"))
        op.add_column("artifacts", sa.Column("owner_review_note", sa.Text(), nullable=True))
        op.add_column("artifacts", sa.Column("owner_reviewed_at", sa.DateTime(timezone=True), nullable=True))
        op.alter_column("artifacts", "owner_review_state", server_default=None)


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts", recreate="always") as batch_op:
            batch_op.drop_column("owner_reviewed_at")
            batch_op.drop_column("owner_review_note")
            batch_op.drop_column("owner_review_state")
    else:
        op.drop_column("artifacts", "owner_reviewed_at")
        op.drop_column("artifacts", "owner_review_note")
        op.drop_column("artifacts", "owner_review_state")
