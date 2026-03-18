"""
Generate Reports - Fetches data from in-memory SQLite and generates Excel/CSV analysis reports.
Run data_to_sqlite.py first to populate the database.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Annotated, List

import pandas as pd

# agenticai imports for in-memory SQLite access
from agenticai.a2a.context import get_current_session_id
from agenticai.tools import tool_registry
from agenticai.tools.examples.sql_dataframe_tools import (
    _ensure_sqlite_connection,
)

from .phone_normalizer import normalize_phone, country_to_region
from .table_utils import is_invoice_table

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
OUTPUT_DIR = "/mnt/agentfiles/output"  # Use volume mount path for persistence
EXPECTED_MONTHS = 3  # Number of months being analyzed

# Column names
EMPLOYEE_PHONE_COL = "Wireless number"
INVOICE_PHONE_COL = "phone"

# ============================================================================
# CANONICAL INVOICE SCHEMA
# ============================================================================

# The exact column names present in every invoice CSV produced by the extractor.
# All downstream SQL queries reference these names directly — no alias mapping needed.
INVOICE_CANONICAL_COLUMNS: List[str] = [
    "phone",
    "source_pages",
    "billing_period",
    "data_usage_used",
    "voice_minutes_used",
    "messages_sent",
    "total_current_charges",
]

# ============================================================================
# SQL QUERIES (inline - no config file needed)
# ============================================================================

# Query to get phones with ANY usage in an invoice table.
# References the exact canonical column names from the invoice CSV.
# CAST(... AS REAL) converts '0', '0.0', '0.00' all to numeric 0 for comparison,
# avoiding false positives from string representation differences (e.g. 0 vs 0.0).
SQL_PHONES_WITH_USAGE = """
SELECT DISTINCT phone as phone_number
FROM {table}
WHERE (
    (voice_minutes_used IS NOT NULL AND voice_minutes_used != '--' AND voice_minutes_used != ''
        AND CAST(REPLACE(voice_minutes_used, ',', '.') AS REAL) != 0)
    OR (messages_sent IS NOT NULL AND messages_sent != '--' AND messages_sent != ''
        AND CAST(REPLACE(messages_sent, ',', '.') AS REAL) != 0)
    OR (data_usage_used IS NOT NULL AND data_usage_used != '--' AND data_usage_used != ''
        AND data_usage_used != '0.000GB' AND data_usage_used != '.000GB'
        AND CAST(REPLACE(REPLACE(REPLACE(REPLACE(data_usage_used, 'GB', ''), 'MB', ''), 'KB', ''), ',', '.') AS REAL) != 0)
)
"""

# ============================================================================
# REPORT GENERATOR CLASS
# ============================================================================

_MONTH_ABBR = [
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
]


def _extract_billing_month(bp: str) -> str:
    """Return a 3-letter month abbreviation from any supported billing_period format.
    Supported formats:
      - English month name  : 'OCT 1 2025 - OCT 31 2025'  → 'OCT'
      - dd.mm.yyyy (Telekom): '01.12.2025 31.12.2025'     → 'DEC'
      - dd/mm/yyyy (VIVO)  : '01/12/2025 31/12/2025'     → 'DEC'
      - mm/yyyy or mm-yyyy : '12/2025'                   → 'DEC'
    """
    bp = bp.strip()
    if not bp:
        return ""
    first = bp.split()[0].upper()
    # English 3-letter month abbreviation already in list
    if first in _MONTH_ABBR:
        return first
    # dd.mm.yyyy or dd-mm-yyyy
    for sep in (".", "-"):
        parts = first.split(sep)
        if len(parts) == 3 and parts[1].isdigit():
            m = int(parts[1])
            if 1 <= m <= 12:
                return _MONTH_ABBR[m - 1]
    # dd/mm/yyyy
    parts = first.split("/")
    if len(parts) == 3 and parts[1].isdigit():
        m = int(parts[1])
        if 1 <= m <= 12:
            return _MONTH_ABBR[m - 1]
    # mm/yyyy or mm-yyyy (two-part date)
    for sep in ("/", "-"):
        parts = first.split(sep)
        if len(parts) == 2 and parts[0].isdigit():
            m = int(parts[0])
            if 1 <= m <= 12:
                return _MONTH_ABBR[m - 1]
    return ""


# Device usage types that are considered "functional" (e.g., lifts, alarms).
# These assets are expected to have zero usage and are reported separately
# from employee contracts so ops teams can distinguish actionable savings.
FUNCTIONAL_USAGE_TYPES = {"functional"}


def _split_functional(df: pd.DataFrame):
    """Split a zero-usage DataFrame into (non_functional, functional) based on
    the DV_U_TYPE_OF_USAGE column from Databricks.
    - Non-functional: actionable — personal / non-personal contracts that can be cancelled.
    - Functional: informational — lifts, alarms, emergency lines; zero usage is expected.
    - Invoice-only rows (no employee record) have no DV_U_TYPE_OF_USAGE and are
      always placed in non-functional so they remain actionable for the ops team.
    """
    if df.empty or "DV_U_TYPE_OF_USAGE" not in df.columns:
        return df.copy(), pd.DataFrame(columns=df.columns if not df.empty else [])
    is_functional = (
        df["DV_U_TYPE_OF_USAGE"].fillna("").str.strip().str.lower()
        .isin(FUNCTIONAL_USAGE_TYPES)
    )
    return df[~is_functional].copy(), df[is_functional].copy()


class ReportGenerator:
    def __init__(self, default_region: str = "US", vendor: str = ""):
        self.session_id = get_current_session_id()
        if not self.session_id:
            raise RuntimeError(
                "No active session ID - this requires A2A session context"
            )
        self.conn = _ensure_sqlite_connection(self.session_id)
        self.output_dir = Path(OUTPUT_DIR)/ self.session_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_region = default_region
        self.vendor = vendor.lower().strip() if vendor else ""
        logger.info(f"Connected to in-memory SQLite for session: {self.session_id}")
        logger.info(f"Phone normalization default region: {self.default_region}")
        logger.info(f"Vendor: {self.vendor or '(not specified)'}")

    def close(self):
        # Connection is managed by agenticai session, no explicit close needed
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def query(self, sql, params=None):
        """Execute SQL query and return DataFrame."""
        if params:
            return pd.read_sql(sql, self.conn, params=params)
        return pd.read_sql(sql, self.conn)

    def get_all_tables(self):
        """Get list of all tables in database."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        return [row[0] for row in cursor.fetchall()]

    def get_invoice_tables(self):
        """Get list of invoice tables only (using shared table naming utility)."""
        return [t for t in self.get_all_tables() if is_invoice_table(t)]

    # ========================================================================
    # ANALYSIS FUNCTIONS
    # ========================================================================

    def detect_zero_usage_users(self):
        """Find users with zero usage across ALL invoice months."""
        print(f"\n{'='*60}")
        print("ZERO USAGE DETECTION")
        print("=" * 60)

        invoice_tables = self.get_invoice_tables()
        if not invoice_tables:
            print("No invoice tables found")
            return pd.DataFrame()

        print(f"Invoice tables: {invoice_tables}")

        # Get phones in ALL invoice tables (intersection)
        phones_in_all = None
        for table in invoice_tables:
            df = self.query(
                f"SELECT DISTINCT {INVOICE_PHONE_COL} as phone_number FROM {table}"
            )
            table_phones = set(df["phone_number"].dropna())
            phones_in_all = (
                table_phones if phones_in_all is None else phones_in_all & table_phones
            )

        if not phones_in_all:
            print("No phones found in all tables")
            return pd.DataFrame()

        print(f"Phones in ALL invoices: {len(phones_in_all)}")

        # Find phones with ANY usage in each table and remove from zero usage set
        zero_usage_phones = phones_in_all.copy()
        for table in invoice_tables:
            df = self.query(SQL_PHONES_WITH_USAGE.format(table=table))
            phones_with_usage = set(df["phone_number"].dropna())
            zero_usage_phones -= phones_with_usage
            print(f"  {table}: {len(phones_with_usage)} phones with usage")

        if not zero_usage_phones:
            print("No zero usage users found")
            return pd.DataFrame()

        print(f"Zero usage phones: {len(zero_usage_phones)}")

        # ── Step 1: Enrich zero-usage phones with employee DB data ──────────────
        # _get_employee_details performs an inner-join on phone_number against the
        # Databricks employee tables.  Only phones that have a matching employee row
        # are returned — phones that exist only in invoices are silently dropped.
        # Those invoice-only phones are recovered in Step 2.
        matched = self._get_employee_details(list(zero_usage_phones))
        matched = self._add_total_cost(matched, invoice_tables)

        # ── Step 2: Recover invoice-only zero-usage phones ───────────────────────
        # Subtract the phones that _get_employee_details actually returned from the
        # full zero-usage set.  Anything remaining is "invoice-only": either an
        # ex-employee, a SIM not yet registered in the HR system, or a data-entry
        # error on the invoice side.
        matched_phones   = set(matched["phone_number"]) if not matched.empty else set()
        unmatched_phones = list(zero_usage_phones - matched_phones)

        # ── Step 3: Tag each row with in_employee_data = "Yes" / "No" ────────────
        # This column lets the Ops team instantly distinguish:
        #   "Yes" → employee record found → contract owner is identifiable
        #   "No"  → invoice-only phone   → no HR data, manual investigation needed
        if not matched.empty:
            matched["in_employee_data"] = "Yes"

        if unmatched_phones:
            # Build a minimal DataFrame for invoice-only rows.
            # These rows carry no employee columns (name, department, etc.) so
            # only phone_number + total_cost fields will be populated in the output.
            unmatched = pd.DataFrame({"phone_number": unmatched_phones})
            unmatched = self._add_total_cost(unmatched, invoice_tables)
            unmatched["in_employee_data"] = "No"
            # deletion_reason mirrors the format used for matched rows so the
            # final CSV/Excel output is consistent across both row types.
            unmatched["deletion_reason"] = "Zero Usage (Invoice Only - Not in employee records)"
            print(f"  {len(unmatched_phones)} zero-usage phones are invoice-only (no employee record)")

            # Concatenate employee-linked and invoice-only rows into one DataFrame.
            # ignore_index=True resets the index so no duplicate index values appear.
            result = pd.concat([matched, unmatched], ignore_index=True)
        else:
            result = matched

        # ── Step 4: Drop functional devices (lifts, alarms, emergency lines) ────
        # Functional devices are expected to have zero usage — they are NOT
        # actionable savings candidates and must not inflate the savings figures.
        # They are dropped silently here; each dropped number is logged so the
        # ops team can audit the exclusion if needed.
        non_functional, functional = _split_functional(result)
        if not functional.empty:
            for phone in functional["phone_number"].dropna():
                logger.info(
                    f"[ZERO_USAGE] Dropping functional device: {phone} "
                    f"(DV_U_TYPE_OF_USAGE=functional — expected zero usage, not actionable)"
                )
            print(
                f"  Dropped {len(functional)} functional device(s) from zero-usage list "
                f"(see logs for phone numbers)"
            )

        print(f"[OK] Found {len(non_functional)} actionable zero usage users "
              f"({len(functional)} functional devices excluded)")
        return non_functional

    def detect_invoice_only_users(self):
        """Find phones in invoices but NOT in employee records."""
        print(f"\n{'='*60}")
        print("INVOICE-ONLY USERS DETECTION")
        print("=" * 60)

        invoice_tables = self.get_invoice_tables()

        # Get all invoice phones
        all_invoice_phones = set()
        for table in invoice_tables:
            df = self.query(
                f"SELECT DISTINCT {INVOICE_PHONE_COL} as phone_number FROM {table}"
            )
            all_invoice_phones.update(df["phone_number"].dropna())

        # Get all employee phones
        emp_df = self.query(
            f'SELECT DISTINCT "{EMPLOYEE_PHONE_COL}" as phone_number FROM Employee_data'
        )
        employee_phones = set(emp_df["phone_number"].dropna())

        # Find difference
        invoice_only = list(all_invoice_phones - employee_phones)

        if not invoice_only:
            print("No invoice-only users found")
            return pd.DataFrame()

        result = pd.DataFrame({"phone_number": invoice_only})
        result = self._add_total_cost(result, invoice_tables)
        result = self._add_months_present(result, invoice_tables)
        result["deletion_reason"] = "Invoice Only (Not in employee records)"

        print(f"[OK] Found {len(result)} invoice-only users")
        return result

    def detect_fraud_cases(self):
        """Find inactive/suspended employees with usage in invoices."""
        print(f"\n{'='*60}")
        print("FRAUD DETECTION")
        print("=" * 60)

        # Get inactive employees — supports both legacy CSV columns AND Databricks columns
        inactive_query = f"""
            SELECT *, "{EMPLOYEE_PHONE_COL}" as phone_number
            FROM Employee_data
            WHERE (
                LOWER("Wireless number status") IN ('s', 'suspended', 'inactive', 'terminated', 'cancelled')
                OR LOWER("Account status indicator") LIKE '%inactive%'
                OR LOWER("Account status indicator") LIKE '%suspended%'
                OR LOWER("Account status indicator") LIKE '%terminated%'
                OR LOWER(COALESCE("U_ACTIVE", '')) = 'false'
                OR LOWER(COALESCE("DV_INSTALL_STATUS", '')) = 'retired'
            )
        """
        inactive_df = self.query(inactive_query)

        if inactive_df.empty:
            print("No inactive employees found")
            return pd.DataFrame()

        print(f"Inactive employees: {len(inactive_df)}")

        # Check which have usage
        invoice_tables = self.get_invoice_tables()
        phone_list = inactive_df["phone_number"].dropna().tolist()
        phones_with_usage = self._phones_with_usage(phone_list, invoice_tables)
        fraud_phones = [p for p in phone_list if p in phones_with_usage]

        if not fraud_phones:
            print("No fraud cases detected")
            return pd.DataFrame()

        result = self._get_employee_details(fraud_phones)
        result = self._add_total_cost(result, invoice_tables)
        result = self._add_months_present(result, invoice_tables)
        result = self._add_page_numbers(result, invoice_tables)

        print(f"[OK] Found {len(result)} potential fraud cases")
        return result

    def detect_employee_only_users(self):
        """Find employees NOT in any invoice."""
        print(f"\n{'='*60}")
        print("EMPLOYEE-ONLY USERS DETECTION")
        print("=" * 60)

        invoice_tables = self.get_invoice_tables()

        # Get all employee phones
        emp_df = self.query(
            f'SELECT DISTINCT "{EMPLOYEE_PHONE_COL}" as phone_number FROM Employee_data WHERE "{EMPLOYEE_PHONE_COL}" IS NOT NULL'
        )
        employee_phones = set(emp_df["phone_number"].dropna())

        # Get all invoice phones
        all_invoice_phones = set()
        for table in invoice_tables:
            df = self.query(
                f"SELECT DISTINCT {INVOICE_PHONE_COL} as phone_number FROM {table}"
            )
            all_invoice_phones.update(df["phone_number"].dropna())

        # Find employees not in invoices
        employee_only = list(employee_phones - all_invoice_phones)

        if not employee_only:
            print("No employee-only users found")
            return pd.DataFrame()

        result = self._get_employee_details(employee_only)
        result["total_cost_all_months"] = 0.0

        print(f"[OK] Found {len(result)} employee-only users")
        return result

    # ========================================================================
    # HELPER FUNCTIONS
    # ========================================================================

    # SQLite has a limit of 999 variables per query; batch IN clauses
    _SQL_BATCH_SIZE = 500

    def _get_employee_details(self, phone_list):
        """Get employee details for given phone numbers (batched to avoid SQLite variable limit)."""
        if not phone_list:
            return pd.DataFrame()
        frames = []
        for i in range(0, len(phone_list), self._SQL_BATCH_SIZE):
            batch = phone_list[i : i + self._SQL_BATCH_SIZE]
            placeholders = ",".join(["?" for _ in batch])
            query = f"""
                SELECT *, "{EMPLOYEE_PHONE_COL}" as phone_number
                FROM Employee_data
                WHERE "{EMPLOYEE_PHONE_COL}" IN ({placeholders})
            """
            frames.append(self.query(query, tuple(batch)))
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def _add_total_cost(self, df, invoice_tables):
        """Add total cost column by summing abs(cost) across all invoice tables."""
        if df.empty:
            df["total_cost_all_months"] = 0.0
            return df

        df = df.copy()
        phone_list = df["phone_number"].dropna().tolist()
        cost_map: dict = {phone: 0.0 for phone in phone_list}

        for table in invoice_tables:
            for i in range(0, len(phone_list), self._SQL_BATCH_SIZE):
                batch = phone_list[i : i + self._SQL_BATCH_SIZE]
                placeholders = ",".join(["?" for _ in batch])
                cost_df = self.query(
                    f"""
                    SELECT {INVOICE_PHONE_COL} as phone,
                           SUM(ABS(CAST(REPLACE(REPLACE(REPLACE(total_current_charges, '$', ''), ',', ''), '-', '') AS REAL))) as cost
                    FROM {table}
                    WHERE {INVOICE_PHONE_COL} IN ({placeholders})
                    GROUP BY {INVOICE_PHONE_COL}
                    """,
                    tuple(batch),
                )
                for _, r in cost_df.iterrows():
                    if r["phone"] in cost_map:
                        cost_map[r["phone"]] += r["cost"] or 0.0

        df["total_cost_all_months"] = df["phone_number"].map(cost_map).fillna(0.0)
        return df

    def _add_months_present(self, df, invoice_tables):
        """Add months_present column.

        Handles multiple billing_period formats via the module-level
        _extract_billing_month helper (English, dd.mm.yyyy, dd/mm/yyyy, mm/yyyy).
        """
        if df.empty:
            df["months_present"] = ""
            return df

        df = df.copy()
        phone_list = df["phone_number"].dropna().tolist()
        months_map: dict = {phone: set() for phone in phone_list}

        for table in invoice_tables:
            for i in range(0, len(phone_list), self._SQL_BATCH_SIZE):
                batch = phone_list[i : i + self._SQL_BATCH_SIZE]
                placeholders = ",".join(["?" for _ in batch])
                result = self.query(
                    f"SELECT DISTINCT {INVOICE_PHONE_COL} as phone, billing_period FROM {table} WHERE {INVOICE_PHONE_COL} IN ({placeholders})",
                    tuple(batch),
                )
                for _, row in result.iterrows():
                    phone = row["phone"]
                    bp = row["billing_period"]
                    if phone in months_map and isinstance(bp, str):
                        m = _extract_billing_month(bp)
                        if m:
                            months_map[phone].add(m)

        def _format_months(phone):
            months = months_map.get(phone, set())
            return ", ".join(
                sorted(months, key=lambda x: _MONTH_ABBR.index(x) if x in _MONTH_ABBR else 999)
            )

        df["months_present"] = df["phone_number"].map(_format_months)
        return df

    def _add_page_numbers(self, df, invoice_tables):
        """Add page numbers from invoices using the canonical 'source_pages' column."""
        if df.empty:
            df["page_numbers"] = ""
            return df

        df = df.copy()
        phone_list = df["phone_number"].dropna().tolist()
        page_map: dict = {phone: {} for phone in phone_list}  # phone -> {month: source_pages}

        for table in invoice_tables:
            for i in range(0, len(phone_list), self._SQL_BATCH_SIZE):
                batch = phone_list[i : i + self._SQL_BATCH_SIZE]
                placeholders = ",".join(["?" for _ in batch])
                result = self.query(
                    f"SELECT DISTINCT {INVOICE_PHONE_COL} as phone, source_pages, billing_period FROM {table} WHERE {INVOICE_PHONE_COL} IN ({placeholders})",
                    tuple(batch),
                )
                for _, r in result.iterrows():
                    phone = r["phone"]
                    if phone in page_map and pd.notna(r.get("source_pages")) and pd.notna(r.get("billing_period")):
                        month = _extract_billing_month(str(r["billing_period"]).strip())
                        if month:
                            page_map[phone][month] = str(r["source_pages"])

        def _format_pages(phone):
            page_info = page_map.get(phone, {})
            sorted_months = sorted(
                page_info.keys(),
                key=lambda x: _MONTH_ABBR.index(x) if x in _MONTH_ABBR else 999,
            )
            return " | ".join(f"{m}: Pg {page_info[m]}" for m in sorted_months)

        df["page_numbers"] = df["phone_number"].map(_format_pages)
        return df

    def _phones_with_usage(self, phone_list, invoice_tables):
        """Return a set of phones that have any usage in any invoice table (batched).
        Queries canonical columns: voice_minutes_used, messages_sent, data_usage_used.
        Uses CAST AS REAL so that 0, 0.0, and 0.00 are all treated as zero — consistent
        with SQL_PHONES_WITH_USAGE.
        """
        if not phone_list:
            return set()
        has_usage: set = set()
        for table in invoice_tables:
            remaining = [p for p in phone_list if p not in has_usage]
            if not remaining:
                break
            for i in range(0, len(remaining), self._SQL_BATCH_SIZE):
                batch = remaining[i : i + self._SQL_BATCH_SIZE]
                placeholders = ",".join(["?" for _ in batch])
                result = self.query(
                    f"""
                    SELECT DISTINCT {INVOICE_PHONE_COL} as phone FROM {table}
                    WHERE {INVOICE_PHONE_COL} IN ({placeholders})
                      AND (
                        (voice_minutes_used IS NOT NULL AND voice_minutes_used != '--' AND voice_minutes_used != ''
                            AND CAST(REPLACE(voice_minutes_used, ',', '.') AS REAL) != 0)
                        OR (messages_sent IS NOT NULL AND messages_sent != '--' AND messages_sent != ''
                            AND CAST(REPLACE(messages_sent, ',', '.') AS REAL) != 0)
                        OR (data_usage_used IS NOT NULL AND data_usage_used != '--' AND data_usage_used != ''
                            AND data_usage_used != '0.000GB' AND data_usage_used != '.000GB'
                            AND CAST(REPLACE(REPLACE(REPLACE(REPLACE(data_usage_used, 'GB', ''), 'MB', ''), 'KB', ''), ',', '.') AS REAL) != 0)
                      )
                    """,
                    tuple(batch),
                )
                has_usage.update(result["phone"].dropna().tolist())
        return has_usage

    # ========================================================================
    # REPORT EXPORT FUNCTIONS
    # ========================================================================

    def export_to_csv(self, df, filename, column_order=None):
        """Export DataFrame to CSV with optional column ordering."""
        if df.empty:
            print(f"[WARN] No data to export for {filename}")
            return

        df_export = df.copy()

        # ── Restore original Databricks phone number for employee-linked rows ────
        # During phone matching, phone_number holds the normalised E.164 string
        # (digits only, used purely for reliable cross-source key comparison).
        # For the exported CSV we prefer the original MOBILE_NUMBER value from
        # Databricks (already E.164 formatted, e.g. "+491715511656") which is
        # what downstream consumers and the Ops team expect to see.
        #
        # IMPORTANT: the boolean mask restricts the override to rows where
        # MOBILE_NUMBER is non-null / non-empty.  Invoice-only zero-usage rows
        # have no employee record so MOBILE_NUMBER = NaN — a plain DataFrame
        # assignment (df["phone_number"] = df["MOBILE_NUMBER"]) would silently
        # wipe those rows to NaN.  The masked approach preserves them.
        if "MOBILE_NUMBER" in df_export.columns:
            mask = df_export["MOBILE_NUMBER"].notna() & (df_export["MOBILE_NUMBER"].astype(str).str.strip() != "")
            df_export.loc[mask, "phone_number"] = df_export.loc[mask, "MOBILE_NUMBER"]

        # Build full name from first/last name if available
        if "FIRST_NAME" in df_export.columns and "LAST_NAME" in df_export.columns:
            df_export["name"] = (
                df_export["FIRST_NAME"].fillna("")
                + " "
                + df_export["LAST_NAME"].fillna("")
            ).str.strip()
        elif (
            "User first name" in df_export.columns
            and "User last name" in df_export.columns
        ):
            df_export["name"] = (
                df_export["User first name"] + " " + df_export["User last name"]
            )

        if column_order:
            available_cols = [c for c in column_order if c in df_export.columns]
            df_export = df_export[available_cols]

        filepath = self.output_dir / filename
        df_export.to_csv(filepath, index=False, encoding="utf-8-sig")
        print(f"[OK] Exported {len(df_export)} rows to {filename}")

    def export_to_excel(self, results_dict, filename="wireless_analysis_report.xlsx"):
        """Export all results to a single Excel file with multiple sheets."""
        filepath = self.output_dir / filename

        with pd.ExcelWriter(filepath, engine="openpyxl") as writer:
            for sheet_name, df in results_dict.items():
                if not df.empty:
                    df = df.copy()
                    # Restore Databricks MOBILE_NUMBER for employee-linked rows only.
                    # Masked assignment prevents overwriting invoice-only rows whose
                    # MOBILE_NUMBER is NaN — see export_to_csv for full explanation.
                    if "MOBILE_NUMBER" in df.columns:
                        mask = df["MOBILE_NUMBER"].notna() & (df["MOBILE_NUMBER"].astype(str).str.strip() != "")
                        df.loc[mask, "phone_number"] = df.loc[mask, "MOBILE_NUMBER"]
                    # Build full name
                    if "FIRST_NAME" in df.columns and "LAST_NAME" in df.columns:
                        df["name"] = (
                            df["FIRST_NAME"].fillna("")
                            + " "
                            + df["LAST_NAME"].fillna("")
                        ).str.strip()
                    elif (
                        "User first name" in df.columns
                        and "User last name" in df.columns
                    ):
                        df["name"] = df["User first name"] + " " + df["User last name"]
                    df.to_excel(writer, sheet_name=sheet_name[:31], index=False)
                    print(f"  - {sheet_name}: {len(df)} rows")

        print(f"[OK] Excel report saved to: {filepath}")

    def calculate_savings_summary(self, zero_usage_df, invoice_only_df, fraud_df):
        """Calculate and return savings summary.

        Actionable savings come ONLY from:
          - Zero Usage users (contracts to cancel)
          - Fraud cases (inactive employees still incurring charges)
        Invoice-only users are informational (data quality / ex-employee cleanup)
        but their cost is NOT included in the actionable savings total.
        """

        def get_cost(df):
            if "total_cost_all_months" not in df.columns:
                return 0.0
            return float(df["total_cost_all_months"].abs().sum())

        zero_cost = get_cost(zero_usage_df)
        invoice_cost = get_cost(invoice_only_df)
        fraud_cost = get_cost(fraud_df)

        # Actionable savings = only zero-usage + fraud
        actionable_cost = zero_cost + fraud_cost

        monthly_savings = (
            actionable_cost / EXPECTED_MONTHS if EXPECTED_MONTHS > 0 else 0
        )
        annual_savings = monthly_savings * 12

        return {
            "analysis_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "months_analyzed": EXPECTED_MONTHS,
            "categories": {
                "zero_usage": {
                    "count": len(zero_usage_df),
                    "total_cost": float(zero_cost),
                },
                "invoice_only": {
                    "count": len(invoice_only_df),
                    "total_cost": float(invoice_cost),
                },
                "fraud": {"count": len(fraud_df), "total_cost": float(fraud_cost)},
                "employee_only": {"count": 0, "total_cost": 0.0},
            },
            "summary": {
                "total_issues": len(zero_usage_df)
                + len(invoice_only_df)
                + len(fraud_df),
                "total_cost": float(actionable_cost),
                "total_cost_all_categories": float(
                    zero_cost + invoice_cost + fraud_cost
                ),
                "actionable_cost": float(actionable_cost),
                "monthly_savings": float(monthly_savings),
                "annual_savings": float(annual_savings),
            },
        }

    def _normalize_invoice_tables(self) -> None:
        """
        Trim each invoice table to the canonical 7-column schema.

        The extractor always produces exactly these column names:
          phone, source_pages, billing_period, data_usage_used,
          voice_minutes_used, messages_sent, total_current_charges

        This step drops any extra columns the extractor may have emitted
        and ensures missing canonical columns are filled with None so
        all downstream SQL queries work without further adaptation.
        """
        print(f"\n{'='*60}")
        print("INVOICE TABLE SCHEMA NORMALIZATION")
        print("=" * 60)

        for table in self.get_invoice_tables():
            try:
                df = pd.read_sql(f"SELECT * FROM {table}", self.conn)
                original_cols = list(df.columns)

                # Telekom: 'phone' holds the SIM card (Kartennummer) grouping key,
                # not the actual phone number. The real number is in 'phone_number'.
                # Vendor is passed explicitly from the UI selection — no filename guessing.
                # Drop the SIM card column and promote 'phone_number' → 'phone'.
                if self.vendor == "telekom" and "phone_number" in df.columns:
                    df = df.drop(columns=["phone"], errors="ignore")
                    df = df.rename(columns={"phone_number": "phone"})

                # Fill any missing canonical columns with None
                for col in INVOICE_CANONICAL_COLUMNS:
                    if col not in df.columns:
                        df[col] = None

                # Keep ONLY the canonical columns — drop everything else
                df = df[INVOICE_CANONICAL_COLUMNS].copy()

                # Vivo (Brazil): retain only rows whose phone matches the Brazilian
                # mobile format: DD-9XXXX-XXXX  (e.g. 11-91034-4395).
                #   - 2-digit area code (DDD)
                #   - hyphen
                #   - 9 followed by 4 digits  (9 prefix = Brazilian mobile)
                #   - hyphen
                #   - 4 trailing digits
                # Rows that do not match this pattern are non-phone entries
                # (e.g. account numbers, headers) and must be excluded before
                # any downstream matching runs.
                if self.vendor == "vivo":
                    import re as _re
                    _BR_MOBILE = _re.compile(r"^\d{2}-9\d{4}-\d{4}$")
                    before = len(df)
                    mask = df["phone"].astype(str).str.strip().apply(
                        lambda x: bool(_BR_MOBILE.match(x))
                    )
                    df = df[mask].copy()
                    dropped_rows = before - len(df)
                    print(f"  [Vivo] Filtered out {dropped_rows} non-Brazilian-mobile rows "
                          f"(pattern: DD-9XXXX-XXXX). Kept {len(df)} valid rows.")
                    logger.info(
                        f"[NORMALIZE][Vivo] {table}: dropped {dropped_rows} invalid phone rows, "
                        f"kept {len(df)}"
                    )

                # Overwrite the SQLite table in-place
                df.to_sql(table, self.conn, if_exists="replace", index=False)
                self.conn.commit()

                dropped = [c for c in original_cols if c not in INVOICE_CANONICAL_COLUMNS]
                print(f"  {table}: {len(df)} rows | dropped {len(dropped)} extra col(s): {dropped}")
                logger.info(f"[NORMALIZE] {table}: dropped={dropped} rows={len(df)}")

            except Exception as exc:
                logger.warning(f"[NORMALIZE] Failed for table '{table}': {exc}")
                print(f"  [WARN] Could not normalize table '{table}': {exc}")

    def _normalize_all_phone_columns(self, default_region: str = "US"):
        """
        Normalize phone numbers in BOTH invoice tables and employee table
        so that matching happens on a common E.164 format.

        Invoice 'phone' column: normalized using the country the user selected
        in the UI (e.g. 'BR' for Brazil → '+5511912345678').
        Employee 'Wireless number': already E.164 from Databricks, passed through.
        """
        print(f"\n{'='*60}")
        print(f"PHONE NUMBER NORMALIZATION (region={default_region})")
        print("=" * 60)

        def _normalize_invoice_phone(x):
            """Normalize invoice phone using the user-selected country region,
            and guarantee a leading '+'."""
            n = normalize_phone(str(x), default_region) if pd.notna(x) else None
            if n and not n.startswith("+"):
                n = f"+{n}"
            return n

        # --- Invoice tables ---
        for table in self.get_invoice_tables():
            df = pd.read_sql(
                f"SELECT rowid, {INVOICE_PHONE_COL} FROM {table}", self.conn
            )
            original_count = len(df)
            df["_normalized"] = df[INVOICE_PHONE_COL].apply(_normalize_invoice_phone)
            # Diagnostic: show a sample so mismatches can be spotted in logs
            sample = df[[INVOICE_PHONE_COL, "_normalized"]].dropna().head(5)
            print(f"  [{table}] invoice phone sample (before → after normalization):")
            for _, r in sample.iterrows():
                print(f"    {r[INVOICE_PHONE_COL]!r:35s} → {r['_normalized']!r}")
            # Update in-place via SQL
            cursor = self.conn.cursor()
            updated = 0
            for _, row in df.iterrows():
                if (
                    row["_normalized"]
                    and str(row[INVOICE_PHONE_COL]) != row["_normalized"]
                ):
                    cursor.execute(
                        f"UPDATE {table} SET {INVOICE_PHONE_COL} = ? WHERE rowid = ?",
                        (row["_normalized"], row["rowid"]),
                    )
                    updated += 1
            self.conn.commit()
            print(f"  {table}: normalized {updated}/{original_count} phone numbers")

        # --- Employee table ---
        try:
            emp_df = pd.read_sql(
                f'SELECT rowid, "{EMPLOYEE_PHONE_COL}" FROM Employee_data',
                self.conn,
            )
            original_count = len(emp_df)
            # Use the same default_region as invoice phones so both sides produce
            # the same E.164 format for numbers that lack a '+' country prefix.
            # Previously this defaulted to "US", causing German/Brazilian numbers
            # without a '+' to be parsed incorrectly → false "User Not Found" matches.
            emp_df["_normalized"] = emp_df[EMPLOYEE_PHONE_COL].apply(
                lambda x: normalize_phone(str(x), default_region) if pd.notna(x) else None
            )
            # Diagnostic: show a sample so format mismatches can be spotted in logs
            sample = emp_df[[EMPLOYEE_PHONE_COL, "_normalized"]].dropna().head(5)
            print(f"  [Employee_data] phone sample (before → after normalization):")
            for _, r in sample.iterrows():
                print(f"    {str(r[EMPLOYEE_PHONE_COL])!r:35s} → {r['_normalized']!r}")
            cursor = self.conn.cursor()
            updated = 0
            for _, row in emp_df.iterrows():
                if (
                    row["_normalized"]
                    and str(row[EMPLOYEE_PHONE_COL]) != row["_normalized"]
                ):
                    cursor.execute(
                        f'UPDATE Employee_data SET "{EMPLOYEE_PHONE_COL}" = ? WHERE rowid = ?',
                        (row["_normalized"], row["rowid"]),
                    )
                    updated += 1
            self.conn.commit()
            print(
                f"  Employee_data: normalized {updated}/{original_count} phone numbers"
            )
        except Exception as e:
            print(f"  [WARN] Could not normalize employee phones: {e}")

    def generate_all_reports(self):
        """Run all analyses and generate reports."""
        print("\n" + "=" * 60)
        print(" WIRELESS DATA ANALYSIS - REPORT GENERATOR")
        print("=" * 60)

        # Step 1: Normalize invoice table schemas to the 7-column canonical schema.
        # This maps vendor-specific column names (e.g. 'phone_number', 'total_current_charges')
        # to the names all downstream SQL queries hardcode against.
        self._normalize_invoice_tables()

        # Step 2: Normalize phone number formats on both sides BEFORE any matching/analysis
        self._normalize_all_phone_columns(self.default_region)

        # Run all analyses
        zero_usage_df = self.detect_zero_usage_users()
        invoice_only_df = self.detect_invoice_only_users()
        fraud_df = self.detect_fraud_cases()
        employee_only_df = self.detect_employee_only_users()

        # Calculate savings
        savings = self.calculate_savings_summary(
            zero_usage_df, invoice_only_df, fraud_df
        )
        # Backfill employee_only count (not used for savings but shown in UI)
        savings["categories"]["employee_only"]["count"] = len(employee_only_df)

        # Export to CSV files
        print(f"\n{'='*60}")
        print("EXPORTING CSV REPORTS")
        print("=" * 60)

        # Columns for outputs that contain Databricks employee records.
        # phone_number is overridden to MOBILE_NUMBER (original E.164 format) in export_to_csv/excel.
        # Columns are ordered: identity → contact → org → SIM status → invoice fields → cost.
        employee_output_cols = [
            # --- Identity ---
            "phone_number",  # overridden to MOBILE_NUMBER (original Databricks format)
            "name",  # derived: FIRST_NAME + LAST_NAME
            "FIRST_NAME",
            "LAST_NAME",
            "EMAIL",  # from snow_sys_user_view join
            # --- Organisation ---
            "DV_OWNED_BY",  # employee display name (from SIM card view)
            "DV_ASSIGNED_TO",  # assigned-to display name
            "DV_COMPANY",  # company (from SIM card view)
            "DV_DEPARTMENT",  # department (from snow_sys_user_view)
            "DV_TITLE",  # job title (from snow_sys_user_view)
            "DV_SUPPORT_GROUP",  # support group (from SIM card view)
            "U_COUNTRY",  # country
            # --- SIM / account status ---
            "U_NUMBER",  # SIM / asset number
            "U_ACTIVE",  # active flag (from SIM card view)
            "ACTIVE",  # active flag (from snow_sys_user_view)
            "DV_INSTALL_STATUS",  # install status
            "Wireless number status",
            "Account status indicator",
            # --- Invoice-side fields (may be absent for employee-only) ---
            "Cost center",
            "Account activation date",
            "Device type",
            "Device model",
            "Current price plan",
            "Price plan amount",
            # --- Financials ---
            "total_cost_all_months",
        ]

        # in_employee_data is placed as the second column (immediately after
        # phone_number) so reviewers can scan at a glance whether each zero-usage
        # number has a linked employee record — without having to scroll right.
        self.export_to_csv(
            zero_usage_df, "1_ZERO_USAGE_USERS.csv",
            ["phone_number", "in_employee_data"] + [c for c in employee_output_cols if c != "phone_number"],
        )
        self.export_to_csv(
            invoice_only_df,
            "2_USER_NOT_FOUND.csv",
            [
                "phone_number",
                "total_cost_all_months",
                "deletion_reason",
                "months_present",
            ],
        )
        self.export_to_csv(
            fraud_df,
            "3_INACTIVE_USERS.csv",
            employee_output_cols + ["months_present", "page_numbers"],
        )
        self.export_to_csv(
            employee_only_df, "4_EMPLOYEE_ONLY_USERS.csv", employee_output_cols
        )

        # Export to Excel (all in one file) with timestamped filename
        print(f"\n{'='*60}")
        print("EXPORTING EXCEL REPORT")
        print("=" * 60)

        # Generate timestamped filename
        excel_filename = (
            f"mobile_contract_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

        self.export_to_excel(
            {
                "Zero Usage": zero_usage_df,
                "Invoice Only": invoice_only_df,
                "Fraud Cases": fraud_df,
                "Employee Only": employee_only_df,
            },
            filename=excel_filename,
        )

        # Add filename to savings dict for later return
        savings["excel_filename"] = excel_filename
        savings["output_dir"] = str(self.output_dir)

        # Save JSON summary
        json_path = self.output_dir / "savings_summary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(savings, f, indent=2)
        print(f"[OK] Savings summary saved to: savings_summary.json")

        # Print summary
        print(f"\n{'='*60}")
        print("SAVINGS SUMMARY")
        print("=" * 60)
        print(
            f"Zero Usage Users: {savings['categories']['zero_usage']['count']} (${savings['categories']['zero_usage']['total_cost']:,.2f})"
        )
        print(
            f"Invoice Only Users: {savings['categories']['invoice_only']['count']} (${savings['categories']['invoice_only']['total_cost']:,.2f})  [informational]"
        )
        print(
            f"Fraud Cases: {savings['categories']['fraud']['count']} (${savings['categories']['fraud']['total_cost']:,.2f})"
        )
        print(f"Employee Only: {savings['categories']['employee_only']['count']}")
        print(f"\nTotal Issues: {savings['summary']['total_issues']}")
        print(
            f"Actionable Cost (Zero Usage + Fraud): ${savings['summary']['actionable_cost']:,.2f}"
        )
        print(
            f"Estimated Monthly Savings: ${savings['summary']['monthly_savings']:,.2f}"
        )
        print(f"Estimated Annual Savings: ${savings['summary']['annual_savings']:,.2f}")

        return savings


@tool_registry.register(
    name="generate_mobile_contract_reports",
    description="Generate comprehensive analysis reports from invoice and employee data in SQLite. Detects zero usage users, invoice-only users, fraud cases, and calculates cost savings. Returns savings summary with total issues and potential savings.",
    tags=["reporting", "analysis", "excel", "savings"],
    requires_context=True,
)
def generate_mobile_contract_reports(country: str = "", vendor: str = "") -> str:
    """
    Generate comprehensive mobile contract analysis reports.

    This tool analyzes data from both Phase 1 (invoice table) and Phase 2 (Employee_data table)
    to identify optimization opportunities and generate Excel reports.

    Analysis performed:
    1. Zero Usage Users - Employees with no usage across all invoice months
    2. Invoice Only Users - Phone numbers in invoices but not in employee records
    3. Fraud Cases - Inactive/suspended employees with usage in invoices
    4. Employee Only Users - Employees not appearing in any invoice

    Args:
        country: Human-readable country name or ISO-3166-1 alpha-2 code selected
                 by the user in the UI (e.g. "Germany", "DE", "Brazil", "BR").
                 Used to determine the default phone-number region so that numbers
                 without a leading '+' country code are normalised correctly.
                 Defaults to empty string → falls back to 'US' normalisation.
                 Pass the SAME value the user selected before calling
                 invoice_pdf_to_tables in Phase 1.

    Outputs:
    - Excel file with multiple sheets (one per category)
    - JSON summary with savings calculations
    - All files saved to 'output/' directory

    Returns:
        JSON string with:
        - success: bool
        - total_issues: Total number of optimization opportunities found
        - total_cost: Total monthly cost of issues
        - monthly_savings: Estimated monthly savings
        - annual_savings: Estimated annual savings
        - categories: Breakdown by category (zero_usage, invoice_only, fraud_cases)
        - output_dir: Directory where reports were saved
        - excel_file: Name of generated Excel report

    Example:
        >>> generate_mobile_contract_reports(country="Germany")
        {"success": true, "total_issues": 45, "monthly_savings": 4500.00, ...}
    """
    logger.info("[TOOL] generate_mobile_contract_reports CALLED")

    try:
        # Get session ID
        session_id = get_current_session_id()
        if not session_id:
            return json.dumps(
                {
                    "success": False,
                    "error": "No active session ID",
                    "message": "Tool requires A2A session context",
                }
            )

        logger.info(f"[TOOL] Session ID: {session_id}")

        # Resolve the UI-selected country to an ISO-3166-1 alpha-2 region code
        # for phone-number normalisation.  The agent passes the same country value
        # the user chose in the UI dropdown — no SQLite round-trip needed.
        default_region = "US"  # safe fallback when country is absent or unrecognised
        if country and country.lower() not in ("not specified", "unknown", "none", ""):
            detected_region = country_to_region(country)
            if detected_region:
                default_region = detected_region
                logger.info(f"[TOOL] Country '{country}' → region '{default_region}' for phone normalization")
            else:
                logger.warning(f"[TOOL] Country '{country}' not in region map — falling back to 'US'")
        else:
            logger.warning("[TOOL] No country provided — falling back to 'US' for phone normalization")

        # Generate reports
        with ReportGenerator(default_region=default_region, vendor=vendor) as generator:
            savings = generator.generate_all_reports()

        # Add metadata
        result = {
            "success": True,
            "total_issues": savings["summary"]["total_issues"],
            "actionable_cost": savings["summary"]["actionable_cost"],
            "monthly_savings": savings["summary"]["monthly_savings"],
            "annual_savings": savings["summary"]["annual_savings"],
            "categories": {
                "zero_usage": {
                    "count": savings["categories"]["zero_usage"]["count"],
                    "cost": savings["categories"]["zero_usage"]["total_cost"],
                },
                "invoice_only": {
                    "count": savings["categories"]["invoice_only"]["count"],
                    "cost": savings["categories"]["invoice_only"]["total_cost"],
                },
                "fraud_cases": {
                    "count": savings["categories"]["fraud"]["count"],
                    "cost": savings["categories"]["fraud"]["total_cost"],
                },
            },
            "output_dir": savings["output_dir"],
            "excel_file": savings["excel_filename"],
            "message": f"Successfully generated reports with {savings['summary']['total_issues']} optimization opportunities. Estimated annual savings: ${savings['summary']['annual_savings']:,.2f}",
        }

        logger.info(
            f"[TOOL] generate_mobile_contract_reports SUCCESS: {result['message']}"
        )
        return json.dumps(result)

    except Exception as e:
        error_msg = f"Failed to generate reports: {str(e)}"
        logger.error(f"[TOOL] generate_mobile_contract_reports ERROR: {error_msg}")
        import traceback

        traceback.print_exc()
        return json.dumps({"success": False, "error": str(e), "message": error_msg})


def main():
    """Main entry point - generate all reports from in-memory SQLite."""
    try:
        with ReportGenerator() as generator:
            generator.generate_all_reports()

        print(f"\nAll reports generated in: {OUTPUT_DIR}/")
        return 0
    except RuntimeError as e:
        print(f"ERROR: {e}")
        print("Ensure data_to_sqlite.py has been run in the same session to load data.")
        return 1


if __name__ == "__main__":
    exit(main())
