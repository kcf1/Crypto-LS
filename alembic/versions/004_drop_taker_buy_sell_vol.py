"""Drop taker_buy_sell_vol table (Binance endpoint is Coin-M only, not USDT-M).

Revision ID: 004
Revises: 003
Create Date: 2026-01-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_taker_buy_sell_vol_symbol_period", table_name="taker_buy_sell_vol")
    op.drop_table("taker_buy_sell_vol")


def downgrade() -> None:
    op.create_table(
        "taker_buy_sell_vol",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("buy_sell_ratio", sa.Float(), nullable=False),
        sa.Column("buy_vol", sa.Float(), nullable=False),
        sa.Column("sell_vol", sa.Float(), nullable=False),
        sa.Column("buy_vol_value", sa.Float(), nullable=False),
        sa.Column("sell_vol_value", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_taker_buy_sell_vol_symbol_period",
        "taker_buy_sell_vol",
        ["symbol", "period"],
        unique=False,
    )
