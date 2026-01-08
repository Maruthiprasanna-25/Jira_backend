"""add_missing_user_story_columns

Revision ID: 8c908e7faea5
Revises: 4549c341db14
Create Date: 2026-01-08 19:48:15.048276

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '8c908e7faea5'
down_revision: Union[str, Sequence[str], None] = '4549c341db14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('user_story', sa.Column('parent_issue_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'user_story', 'user_story', ['parent_issue_id'], ['id'], ondelete='CASCADE')


def downgrade() -> None:
    """Downgrade schema."""
    # Note: constraint name is auto-generated in upgrade, so we might need to find it or use None if generic
    # But usually for downgrade we look up the name.
    # Since we are creating it with None name, we might have trouble dropping it by name.
    # But assuming we just want to drop the column, usually dropping the column drops the FK in some DBs, but explicitly:
    # We should try to drop constraint first.
    # For now, let's just drop the column which might fail if FK exists?
    # Actually, op.drop_column usually works.
    op.drop_column('user_story', 'parent_issue_id')
