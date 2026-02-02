"""Add futures market data tables: basis, global_long_short_account, top_long_short_account, top_long_short_position, taker_buy_sell_vol.

Revision ID: 003
Revises: 002
Create Date: 2026-01-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Basis
    op.create_table(
        "basis",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("basis_rate", sa.Float(), nullable=False),
        sa.Column("basis", sa.Float(), nullable=False),
        sa.Column("futures_price", sa.Float(), nullable=False),
        sa.Column("index_price", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_basis_symbol_period",
        "basis",
        ["symbol", "period"],
        unique=False,
    )

    # Global Long/Short Account Ratio
    op.create_table(
        "global_long_short_account",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("long_short_ratio", sa.Float(), nullable=False),
        sa.Column("long_account", sa.Float(), nullable=False),
        sa.Column("short_account", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_global_long_short_account_symbol_period",
        "global_long_short_account",
        ["symbol", "period"],
        unique=False,
    )

    # Top Trader Long/Short Account Ratio
    op.create_table(
        "top_long_short_account",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("long_short_ratio", sa.Float(), nullable=False),
        sa.Column("long_account", sa.Float(), nullable=False),
        sa.Column("short_account", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_top_long_short_account_symbol_period",
        "top_long_short_account",
        ["symbol", "period"],
        unique=False,
    )

    # Top Trader Long/Short Position Ratio
    op.create_table(
        "top_long_short_position",
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("period", sa.String(), nullable=False),
        sa.Column("timestamp", sa.BigInteger(), nullable=False),
        sa.Column("long_short_ratio", sa.Float(), nullable=False),
        sa.Column("long_position", sa.Float(), nullable=False),
        sa.Column("short_position", sa.Float(), nullable=False),
        sa.PrimaryKeyConstraint("symbol", "period", "timestamp"),
    )
    op.create_index(
        "ix_top_long_short_position_symbol_period",
        "top_long_short_position",
        ["symbol", "period"],
        unique=False,
    )

    # Taker Buy/Sell Volume
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


def downgrade() -> None:
    op.drop_index("ix_taker_buy_sell_vol_symbol_period", table_name="taker_buy_sell_vol")
    op.drop_table("taker_buy_sell_vol")
    op.drop_index("ix_top_long_short_position_symbol_period", table_name="top_long_short_position")
    op.drop_table("top_long_short_position")
    op.drop_index("ix_top_long_short_account_symbol_period", table_name="top_long_short_account")
    op.drop_table("top_long_short_account")
    op.drop_index("ix_global_long_short_account_symbol_period", table_name="global_long_short_account")
    op.drop_table("global_long_short_account")
    op.drop_index("ix_basis_symbol_period", table_name="basis")
    op.drop_table("basis")
