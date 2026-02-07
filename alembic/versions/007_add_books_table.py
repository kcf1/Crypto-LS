"""Add books table and foreign key constraints.

Revision ID: 007
Revises: 006
Create Date: 2025-02-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create books table
    op.create_table(
        "books",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("venue", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    
    # Create indexes
    op.create_index("ix_books_venue", "books", ["venue"], unique=False)
    op.create_index("ix_books_active", "books", ["is_active"], unique=False)
    
    # Populate books table with existing book_ids from all tables
    # This ensures all existing book_ids have entries in books table
    conn = op.get_bind()
    
    # Get current timestamp
    import time
    current_timestamp = int(time.time() * 1000)
    
    # Collect all unique book_ids with their venues
    # We need to handle positions table separately since it doesn't have venue
    book_venues = {}
    
    # From orders
    result = conn.execute(text("SELECT DISTINCT book_id, venue FROM orders"))
    for row in result:
        book_id, venue = row[0], row[1]
        if book_id not in book_venues:
            book_venues[book_id] = venue
    
    # From trades
    result = conn.execute(text("SELECT DISTINCT book_id, venue FROM trades"))
    for row in result:
        book_id, venue = row[0], row[1]
        if book_id not in book_venues:
            book_venues[book_id] = venue
    
    # From balances
    result = conn.execute(text("SELECT DISTINCT book_id, venue FROM balances"))
    for row in result:
        book_id, venue = row[0], row[1]
        if book_venues.get(book_id) != venue:
            # If book_id exists with different venue, use first one found
            if book_id not in book_venues:
                book_venues[book_id] = venue
    
    # From adjustments
    result = conn.execute(text("SELECT DISTINCT book_id, venue FROM adjustments"))
    for row in result:
        book_id, venue = row[0], row[1]
        if book_id not in book_venues:
            book_venues[book_id] = venue
    
    # From positions (no venue, use default)
    result = conn.execute(text("SELECT DISTINCT book_id FROM positions"))
    for row in result:
        book_id = row[0]
        if book_id not in book_venues:
            book_venues[book_id] = "binance_spot"  # Default venue
    
    # Insert books (use INSERT ... ON CONFLICT for PostgreSQL, or check for SQLite)
    for book_id, venue in book_venues.items():
        # Generate display name from book_id
        name = book_id.replace("_", " ").title() + " Book"
        
        # Check if book already exists (for idempotency)
        existing = conn.execute(
            text("SELECT id FROM books WHERE id = :book_id"),
            {"book_id": book_id}
        ).fetchone()
        
        if not existing:
            conn.execute(
                text("""
                    INSERT INTO books (id, name, venue, is_active, created_at, created_by)
                    VALUES (:id, :name, :venue, :is_active, :created_at, :created_by)
                """),
                {
                    "id": book_id,
                    "name": name,
                    "venue": venue,
                    "is_active": True,
                    "created_at": current_timestamp,
                    "created_by": "migration",
                }
            )
    
    # Ensure "default" book exists
    default_exists = conn.execute(
        text("SELECT id FROM books WHERE id = 'default'")
    ).fetchone()
    
    if not default_exists:
        conn.execute(
            text("""
                INSERT INTO books (id, name, venue, is_active, created_at, created_by, description)
                VALUES ('default', 'Default Book', 'binance_spot', true, :created_at, 'system', 'Main trading book')
            """),
            {"created_at": current_timestamp}
        )
    
    conn.commit()
    
    # Add foreign key constraints
    # Note: PostgreSQL supports ON DELETE RESTRICT by default
    op.create_foreign_key(
        "fk_orders_book_id",
        "orders",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT"
    )
    
    op.create_foreign_key(
        "fk_trades_book_id",
        "trades",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT"
    )
    
    op.create_foreign_key(
        "fk_positions_book_id",
        "positions",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT"
    )
    
    op.create_foreign_key(
        "fk_balances_book_id",
        "balances",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT"
    )
    
    op.create_foreign_key(
        "fk_adjustments_book_id",
        "adjustments",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT"
    )


def downgrade() -> None:
    # Drop foreign key constraints
    op.drop_constraint("fk_adjustments_book_id", "adjustments", type_="foreignkey")
    op.drop_constraint("fk_balances_book_id", "balances", type_="foreignkey")
    op.drop_constraint("fk_positions_book_id", "positions", type_="foreignkey")
    op.drop_constraint("fk_trades_book_id", "trades", type_="foreignkey")
    op.drop_constraint("fk_orders_book_id", "orders", type_="foreignkey")
    
    # Drop indexes
    op.drop_index("ix_books_active", table_name="books")
    op.drop_index("ix_books_venue", table_name="books")
    
    # Drop books table
    op.drop_table("books")
