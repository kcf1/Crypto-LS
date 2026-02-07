"""add_record_status_to_adjustments

Revision ID: 415e7c6ce82e
Revises: ab1a5935976a
Create Date: 2026-02-06 00:07:49.361007

Add record_status column to adjustments table for tracking data validity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = '415e7c6ce82e'
down_revision: Union[str, None] = 'ab1a5935976a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add record_status column to adjustments table."""
    
    # Add record_status column to adjustments table
    # Values: 'VALID', 'INVALID', 'DELETED', 'CANCELLED'
    # Default: 'VALID' for all existing records
    op.add_column(
        "adjustments",
        sa.Column("record_status", sa.String(), nullable=False, server_default="VALID")
    )
    
    # Set existing records to VALID (explicitly, in case server_default doesn't work)
    conn = op.get_bind()
    conn.execute(text("UPDATE adjustments SET record_status = 'VALID' WHERE record_status IS NULL"))
    
    # Create index for faster filtering
    op.create_index("ix_adjustments_record_status", "adjustments", ["record_status"], unique=False)


def downgrade() -> None:
    """Remove record_status column from adjustments table."""
    
    # Drop index first
    op.drop_index("ix_adjustments_record_status", table_name="adjustments")
    
    # Drop column
    op.drop_column("adjustments", "record_status")
