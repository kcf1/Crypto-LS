"""Add futures data tables: funding_rate, open_interest, liquidations.

Revision ID: 002
Revises: 001
Create Date: 2026-02-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Funding Rate
    op.create_table(
        "funding_rate",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("funding_time", sa.BigInteger(), nullable=False),
        sa.Column("funding_rate", sa.Float(), nullable=False),
        sa.Column("mark_price", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "funding_time"),
    )
    op.create_index(
        "ix_funding_rate_symbol",
        "funding_rate",
        ["symbol"],
        unique=False,
    )

    # Open Interest
    op.create_table(
        "open_interest",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("sum_open_interest", sa.Float(), nullable=False),
        sa.Column("sum_open_interest_value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_open_interest_symbol_period",
        "open_interest",
        ["symbol", "period"],
        unique=False,
    )

    # Liquidations
    op.create_table(
        "liquidations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("time", sa.BigInteger(), nullable=False),
        sa.Column("order_id", sa.BigInteger(), nullable=False),
        sa.Column("side", sa.String(), nullable=False),
        sa.Column("order_type", sa.String(), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("avg_price", sa.Float(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("last_filled_qty", sa.Float(), nullable=False),
        sa.Column("filled_accumulated_qty", sa.Float(), nullable=False),
        sa.Column("trade_time", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_liquidations_symbol_time",
        "liquidations",
        ["symbol", "time"],
        unique=False,
    )
    op.create_index(
        "ix_liquidations_order_id",
        "liquidations",
        ["order_id"],
        unique=True,
    )
    # Note: order_id unique index prevents duplicate liquidation orders


def downgrade() -> None:
    op.drop_index("ix_liquidations_order_id", table_name="liquidations")
    op.drop_index("ix_liquidations_symbol_time", table_name="liquidations")
    op.drop_table("liquidations")
    op.drop_index("ix_open_interest_symbol_period", table_name="open_interest")
    op.drop_table("open_interest")
    op.drop_index("ix_funding_rate_symbol", table_name="funding_rate")
    op.drop_table("funding_rate")
