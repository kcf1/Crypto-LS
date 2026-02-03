"""Add market_cap table for CoinGecko market capitalization data.

Revision ID: 005
Revises: 004
Create Date: 2026-01-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "market_cap",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("market_cap", sa.Float(), nullable=False),
        sa.Column("circulating_supply", sa.Float(), nullable=False),
        sa.Column("total_supply", sa.Float(), nullable=False),
        sa.Column("max_supply", sa.Float(), nullable=True),
        sa.Column("market_cap_rank", sa.Integer(), nullable=True),
        sa.Column("fully_diluted_valuation", sa.Float(), nullable=True),
        sa.Column("current_price", sa.Float(), nullable=False),
        sa.Column("total_volume", sa.Float(), nullable=False),
        sa.Column("high_24h", sa.Float(), nullable=True),
        sa.Column("low_24h", sa.Float(), nullable=True),
        sa.Column("price_change_24h", sa.Float(), nullable=True),
        sa.Column("price_change_percentage_24h", sa.Float(), nullable=True),
        sa.Column("market_cap_change_24h", sa.Float(), nullable=True),
        sa.Column("market_cap_change_percentage_24h", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("symbol", "timestamp"),
    )
    op.create_index(
        "ix_market_cap_symbol",
        "market_cap",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_cap_symbol", table_name="market_cap")
    op.drop_table("market_cap")
