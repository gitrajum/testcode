"""
Shared utility functions for consistent table naming across the pipeline.
Used by: invoice_extractor.py, data_to_sqlite.py, generate_reports.py, Invoice_user_mapping_tool.py
"""

import os
import re
from pathlib import Path

# ============================================================================
# SHARED CONFIGURATION
# ============================================================================
# Central data directory - used by all pipeline components
# Use volume mount path for persistence across container restarts
DATA_DIR = Path("/mnt/agentfiles/data")


def get_data_dir() -> Path:
    """Get the shared data directory path, creating it if needed."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def generate_invoice_table_name(filename: str) -> str:
    """
    Generate a consistent, sanitized table name for invoice data.

    This function ensures the same table name is generated whether called from:
    - invoice_extractor.py (with PDF filename)
    - data_to_sqlite.py (with CSV filename)

    Args:
        filename: Either PDF filename (e.g., 'OCT_Bill.pdf') or
                  CSV filename (e.g., 'OCT_Bill_Invoice.csv')

    Returns:
        Sanitized table name (e.g., 'oct_bill_invoice')

    Examples:
        >>> generate_invoice_table_name('OCT_Bill.pdf')
        'oct_bill_invoice'
        >>> generate_invoice_table_name('OCT_Bill_Invoice.csv')
        'oct_bill_invoice'
        >>> generate_invoice_table_name('DEC Invoice.csv')
        'dec_invoice'
    """
    # Get base name without extension
    base_name = os.path.splitext(os.path.basename(filename))[0]

    # Remove '_Invoice' or '_invoice' suffix if present (from CSV files)
    # This ensures PDF and CSV generate the same base name
    base_name = re.sub(r"_?[Ii]nvoice$", "", base_name)

    # Sanitize: replace non-alphanumeric with underscore, lowercase
    table_name = re.sub(r"[^a-zA-Z0-9]", "_", base_name).lower()

    # Collapse multiple underscores and strip leading/trailing
    table_name = re.sub(r"_+", "_", table_name).strip("_")

    # Handle names starting with digit
    if table_name and table_name[0].isdigit():
        table_name = f"table_{table_name}"

    # Always append _invoice suffix for invoice tables
    return f"{table_name}_invoice"


def generate_invoice_csv_filename(pdf_filename: str) -> str:
    """
    Generate the CSV filename for an invoice PDF.

    Args:
        pdf_filename: PDF filename (e.g., 'OCT_Bill.pdf')

    Returns:
        CSV filename (e.g., 'OCT_Bill_Invoice.csv')
    """
    base_name = os.path.splitext(os.path.basename(pdf_filename))[0]
    return f"{base_name}_Invoice.csv"


def is_invoice_table(table_name: str) -> bool:
    """
    Check if a table name represents an invoice table.

    Args:
        table_name: Name of the table

    Returns:
        True if this is an invoice table
    """
    return table_name.lower().endswith("_invoice")


def get_invoice_csv_path(pdf_filename: str) -> Path:
    """
    Get the full path where invoice CSV should be stored.

    Args:
        pdf_filename: PDF filename or path (e.g., 'OCT_Bill.pdf')

    Returns:
        Full path to CSV file in data directory
    """
    csv_filename = generate_invoice_csv_filename(pdf_filename)
    return get_data_dir() / csv_filename


def invoice_csv_exists(pdf_filename: str) -> bool:
    """
    Check if the invoice CSV already exists on disk.

    Args:
        pdf_filename: PDF filename or path

    Returns:
        True if CSV file exists
    """
    return get_invoice_csv_path(pdf_filename).exists()


def drop_table_if_exists(session_id: str, table_name: str) -> bool:
    """
    Drop a table from in-memory SQLite if it exists.
    Should be called before storing new data to clear stale entries.

    Args:
        session_id: Current session ID
        table_name: Name of the table to drop

    Returns:
        True if table was dropped, False if it didn't exist
    """
    from agenticai.tools.examples.sql_dataframe_tools import _ensure_sqlite_connection

    try:
        conn = _ensure_sqlite_connection(session_id)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        )
        exists = cursor.fetchone() is not None

        if exists:
            cursor.execute(f"DROP TABLE IF EXISTS {table_name}")
            conn.commit()
            return True
        return False
    except Exception:
        return False
