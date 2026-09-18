"""Add provider setting scope uniqueness."""

from alembic import op


revision = "3c2a5f8e1b4d"
down_revision = "250e73df76d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("provider_settings", recreate="always") as batch_op:
            batch_op.create_unique_constraint("uq_provider_setting_scope", ["provider", "scope"])
    else:
        op.create_unique_constraint("uq_provider_setting_scope", "provider_settings", ["provider", "scope"])


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        with op.batch_alter_table("provider_settings", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_provider_setting_scope", type_="unique")
    else:
        op.drop_constraint("uq_provider_setting_scope", "provider_settings", type_="unique")
