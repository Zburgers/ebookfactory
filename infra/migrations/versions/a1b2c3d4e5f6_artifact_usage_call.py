"""Bind generated artifacts to their exact provider usage call."""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "9c7e2a1b4f55"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts", recreate="always") as batch_op:
            batch_op.add_column(sa.Column("usage_call_id", sa.Uuid(), nullable=True))
            batch_op.create_foreign_key("fk_artifacts_usage_call_id", "usage_calls", ["usage_call_id"], ["id"])
    else:
        op.add_column("artifacts", sa.Column("usage_call_id", sa.Uuid(), nullable=True))
        op.create_foreign_key("fk_artifacts_usage_call_id", "artifacts", "usage_calls", ["usage_call_id"], ["id"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("artifacts") as batch_op:
            batch_op.drop_constraint("fk_artifacts_usage_call_id", type_="foreignkey")
            batch_op.drop_column("usage_call_id")
    else:
        op.drop_constraint("fk_artifacts_usage_call_id", "artifacts", type_="foreignkey")
        op.drop_column("artifacts", "usage_call_id")
