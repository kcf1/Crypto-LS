"""Add balances and adjustments tables, book_id and notes columns.

Revision ID: 006
Revises: 005
Create Date: 2026-02-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add book_id and notes columns to orders table
    op.add_column("orders", sa.Column("book_id", sa.String(), nullable=False, server_default="default"))
    op.add_column("orders", sa.Column("notes", sa.String(), nullable=True))
    
    # Add book_id and notes columns to trades table
    op.add_column("trades", sa.Column("book_id", sa.String(), nullable=False, server_default="default"))
    op.add_column("trades", sa.Column("notes", sa.String(), nullable=True))
    
    # Update positions table: drop existing primary key, add book_id and notes
    op.drop_constraint("positions_pkey", "positions", type_="primary")
    op.add_column("positions", sa.Column("book_id", sa.String(), nullable=False, server_default="default"))
    op.add_column("positions", sa.Column("notes", sa.String(), nullable=True))
    op.create_primary_key("positions_pkey", "positions", ["book_id", "symbol"])
    
    # Create balances table
    op.create_table(
        "balances",
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("asset", sa.String(), nullable=False),
        sa.Column("free", sa.Float(), nullable=False, server_default="0"),
        sa.Column("locked", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("venue", "book_id", "asset"),
    )
    op.create_index("ix_balances_venue", "balances", ["venue"], unique=False)
    op.create_index("ix_balances_book_id", "balances", ["book_id"], unique=False)
    
    # Create adjustments table
    op.create_table(
        "adjustments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("book_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("asset_or_symbol", sa.String(), nullable=False),
        sa.Column("delta_or_value", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_adjustments_venue_book_type_created",
        "adjustments",
        ["venue", "book_id", "type", "created_at"],
        unique=False,
    )
    op.create_index("ix_adjustments_venue", "adjustments", ["venue"], unique=False)
    op.create_index("ix_adjustments_book_id", "adjustments", ["book_id"], unique=False)
    
    # Add unique constraints for idempotency (PostgreSQL partial unique index)
    # Note: PostgreSQL supports WHERE clause in unique constraints, but Alembic needs explicit handling
    # We'll create the constraint with a check that exchange_order_id IS NOT NULL
    op.create_index(
        "uq_orders_venue_book_exchange_id",
        "orders",
        ["venue", "book_id", "exchange_order_id"],
        unique=True,
        postgresql_where=sa.text("exchange_order_id IS NOT NULL"),
    )
    op.create_index(
        "uq_trades_venue_book_exchange_id",
        "trades",
        ["venue", "book_id", "exchange_trade_id"],
        unique=True,
        postgresql_where=sa.text("exchange_trade_id IS NOT NULL"),
    )
    
    # Add indexes for query performance
    op.create_index("ix_orders_venue_book_symbol_created", "orders", ["venue", "book_id", "symbol", "created_at"], unique=False)
    op.create_index("ix_orders_book_id", "orders", ["book_id"], unique=False)
    op.create_index("ix_trades_venue_book_symbol_traded", "trades", ["venue", "book_id", "symbol", "traded_at"], unique=False)
    op.create_index("ix_trades_book_id", "trades", ["book_id"], unique=False)
    op.create_index("ix_positions_book_id", "positions", ["book_id"], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index("ix_positions_book_id", table_name="positions")
    op.drop_index("ix_trades_book_id", table_name="trades")
    op.drop_index("ix_trades_venue_book_symbol_traded", table_name="trades")
    op.drop_index("ix_orders_book_id", table_name="orders")
    op.drop_index("ix_orders_venue_book_symbol_created", table_name="orders")
    
    # Drop unique constraints
    op.drop_index("uq_trades_venue_book_exchange_id", table_name="trades")
    op.drop_index("uq_orders_venue_book_exchange_id", table_name="orders")
    
    # Drop adjustments table
    op.drop_index("ix_adjustments_book_id", table_name="adjustments")
    op.drop_index("ix_adjustments_venue", table_name="adjustments")
    op.drop_index("ix_adjustments_venue_book_type_created", table_name="adjustments")
    op.drop_table("adjustments")
    
    # Drop balances table
    op.drop_index("ix_balances_book_id", table_name="balances")
    op.drop_index("ix_balances_venue", table_name="balances")
    op.drop_table("balances")
    
    # Revert positions table changes
    op.drop_constraint("positions_pkey", "positions", type_="primary")
    op.drop_column("positions", "notes")
    op.drop_column("positions", "book_id")
    op.create_primary_key("positions_pkey", "positions", ["symbol"])
    
    # Remove book_id and notes from trades
    op.drop_column("trades", "notes")
    op.drop_column("trades", "book_id")
    
    # Remove book_id and notes from orders
    op.drop_column("orders", "notes")
    op.drop_column("orders", "book_id")
