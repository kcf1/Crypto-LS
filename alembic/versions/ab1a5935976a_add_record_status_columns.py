"""add_record_status_columns

Revision ID: ab1a5935976a
Revises: 007
Create Date: 2026-02-06 00:00:58.613540

Add record_status columns to orders and trades tables for tracking data validity.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = 'ab1a5935976a'
down_revision: Union[str, None] = '007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add record_status columns to orders and trades tables."""
    
    # Add record_status column to orders table
    # Values: 'VALID', 'CANCELLED', 'INVALID', 'DELETED'
    # Default: 'VALID' for all existing records
    op.add_column(
        "orders",
        sa.Column("record_status", sa.String(), nullable=False, server_default="VALID")
    )
    
    # Add record_status column to trades table
    # Values: 'VALID', 'INVALID', 'DELETED'
    # Default: 'VALID' for all existing records
    op.add_column(
        "trades",
        sa.Column("record_status", sa.String(), nullable=False, server_default="VALID")
    )
    
    # Set existing records to VALID (explicitly, in case server_default doesn't work)
    conn = op.get_bind()
    conn.execute(text("UPDATE orders SET record_status = 'VALID' WHERE record_status IS NULL"))
    conn.execute(text("UPDATE trades SET record_status = 'VALID' WHERE record_status IS NULL"))
    
    # Create indexes for faster filtering
    op.create_index("ix_orders_record_status", "orders", ["record_status"], unique=False)
    op.create_index("ix_trades_record_status", "trades", ["record_status"], unique=False)
    
    # For orders: Set record_status based on status field for existing cancelled orders
    # (This is optional - we can keep them as VALID since status already tracks cancellation)
    # Uncomment if you want to mark cancelled orders as CANCELLED in record_status:
    # conn.execute(text("UPDATE orders SET record_status = 'CANCELLED' WHERE status = 'CANCELLED'"))


def downgrade() -> None:
    """Remove record_status columns from orders and trades tables."""
    
    # Drop indexes first
    op.drop_index("ix_trades_record_status", table_name="trades")
    op.drop_index("ix_orders_record_status", table_name="orders")
    
    # Drop columns
    op.drop_column("trades", "record_status")
    op.drop_column("orders", "record_status")
