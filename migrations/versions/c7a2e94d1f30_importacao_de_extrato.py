"""importacao de extrato

Revision ID: c7a2e94d1f30
Revises: b32358bdba4b
Create Date: 2026-10-29 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7a2e94d1f30'
down_revision = 'b32358bdba4b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('receitas', schema=None) as batch_op:
        batch_op.add_column(sa.Column('id_externo', sa.String(length=60), nullable=True))
        batch_op.create_index(batch_op.f('ix_receitas_id_externo'), ['id_externo'], unique=True)


def downgrade():
    with op.batch_alter_table('receitas', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_receitas_id_externo'))
        batch_op.drop_column('id_externo')
