"""
Databricks Employee Data Loader Tool.

Connects to Databricks SQL warehouse, queries the SIM card and sys_user views,
joins them on SYS_ID, normalizes phone numbers, and loads the combined employee
data into the in-memory SQLite table `Employee_data` — replacing the
manual CSV upload flow.

Databricks connection details are read from environment variables:
  DATABRICKS_HOST, DATABRICKS_HTTP_PATH, DATABRICKS_TOKEN,
  DATABRICKS_CATALOG, DATABRICKS_SCHEMA
"""

import json
import logging
import math
import os
from typing import Annotated, Optional

import pandas as pd
from agenticai.a2a.context import get_current_session_id
from agenticai.tools import tool_registry
from agenticai.tools.examples.sql_dataframe_tools import _store_dataframe
from pydantic import Field

from .phone_normalizer import normalize_phone, country_to_region
from .table_utils import drop_table_if_exists

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================
_DEFAULT_HOST = "adb-4071335540424391.11.azuredatabricks.net"
_DEFAULT_HTTP_PATH = "/sql/1.0/warehouses/916c447fdd11cd1e"
_DEFAULT_CATALOG = "efdataonelh_prd"
_DEFAULT_SCHEMA = "generaldiscovery_servicenow_r"
_SIM_TABLE = "snow_cmdb_ci_sim_card_view"
_USER_TABLE = "snow_sys_user_view"

# Batch size for chunked reads (rows per fetch)
_FETCH_BATCH = 50_000


def _get_databricks_connection():
    """Create a Databricks SQL connection from environment variables."""
    from databricks import sql as databricks_sql

    host = os.environ.get("DATABRICKS_HOST", _DEFAULT_HOST)
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", _DEFAULT_HTTP_PATH)
    token = os.environ.get("DATABRICKS_TOKEN", "")

    if not token:
        raise RuntimeError(
            "DATABRICKS_TOKEN environment variable is not set. "
            "Set it to a Databricks Personal Access Token (PAT)."
        )

    return databricks_sql.connect(
        server_hostname=host,
        http_path=http_path,
        access_token=token,
    )


def _query_databricks(sql: str, params=None) -> pd.DataFrame:
    """Execute a SQL query on Databricks and return a DataFrame."""
    conn = _get_databricks_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, parameters=params)
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return pd.DataFrame(rows, columns=columns)
    finally:
        conn.close()


def _build_employee_dataframe(country_filter: Optional[str] = None) -> pd.DataFrame:
    """
    Query Databricks for SIM card + sys_user data, join, normalize phones,
    and return a DataFrame shaped like the old employee CSV so that downstream
    Phase 3 logic works unchanged.

    Columns produced (mapped to match legacy CSV columns):
      phone_number_normalized  – digits-only national number (for matching)
      MOBILE_NUMBER            – original E.164 number from Databricks
      Wireless number          – alias for phone_number_normalized (legacy compat)
      DV_OWNED_BY, DV_ASSIGNED_TO, U_ACTIVE, DV_INSTALL_STATUS,
      U_COUNTRY, DV_COMPANY, U_NUMBER, SYS_ID,
      EMAIL, NAME, FIRST_NAME, LAST_NAME, ACTIVE (user), DV_DEPARTMENT, DV_TITLE
      Wireless number status   – derived from U_ACTIVE / DV_INSTALL_STATUS
      Account status indicator – derived from U_ACTIVE
    """

    catalog = os.environ.get("DATABRICKS_CATALOG", _DEFAULT_CATALOG)
    schema = os.environ.get("DATABRICKS_SCHEMA", _DEFAULT_SCHEMA)
    fq_sim = f"{catalog}.{schema}.{_SIM_TABLE}"
    fq_user = f"{catalog}.{schema}.{_USER_TABLE}"

    # ------------------------------------------------------------------
    # 1. Query SIM card view (primary table with MOBILE_NUMBER)
    # ------------------------------------------------------------------
    sim_sql = f"""
        SELECT
            MOBILE_NUMBER,
            DV_OWNED_BY,
            OWNED_BY,
            DV_ASSIGNED_TO,
            ASSIGNED_TO,
            U_ACTIVE,
            DV_INSTALL_STATUS,
            U_COUNTRY,
            DV_COMPANY,
            U_NUMBER,
            DV_SUPPORT_GROUP,
            SYS_ID AS SIM_SYS_ID
        FROM {fq_sim}
        WHERE MOBILE_NUMBER IS NOT NULL
          AND TRIM(MOBILE_NUMBER) != ''
    """
    if country_filter:
        sim_sql += f" AND UPPER(U_COUNTRY) = '{country_filter.upper()}'"

    logger.info(f"[DATABRICKS] Querying SIM card view: {fq_sim}")
    sim_df = _query_databricks(sim_sql)
    logger.info(f"[DATABRICKS] SIM card rows returned: {len(sim_df)}")

    if sim_df.empty:
        logger.warning("[DATABRICKS] No SIM card rows with a mobile number found")
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # 2. Query sys_user view (for email, name, department, etc.)
    # ------------------------------------------------------------------
    # Determine which SYS_IDs to look up — use OWNED_BY (= sys_user SYS_ID)
    owned_ids = sim_df["OWNED_BY"].dropna().unique().tolist()
    assigned_ids = sim_df["ASSIGNED_TO"].dropna().unique().tolist()
    all_user_ids = list(set(owned_ids + assigned_ids))

    user_df = pd.DataFrame()
    if all_user_ids:
        # Batch the IN clause to avoid overly large queries
        batch_size = 500
        user_frames = []
        for i in range(0, len(all_user_ids), batch_size):
            batch = all_user_ids[i : i + batch_size]
            placeholders = ",".join([f"'{uid}'" for uid in batch])
            user_sql = f"""
                SELECT
                    SYS_ID,
                    EMAIL,
                    NAME,
                    FIRST_NAME,
                    LAST_NAME,
                    ACTIVE,
                    DV_DEPARTMENT,
                    DV_COMPANY AS DV_COMPANY_user,
                    DV_TITLE
                FROM {fq_user}
                WHERE SYS_ID IN ({placeholders})
            """
            batch_df = _query_databricks(user_sql)
            user_frames.append(batch_df)

        if user_frames:
            user_df = pd.concat(user_frames, ignore_index=True).drop_duplicates(
                subset=["SYS_ID"]
            )
            logger.info(f"[DATABRICKS] sys_user rows fetched: {len(user_df)}")

    # ------------------------------------------------------------------
    # 3. Join SIM ← sys_user on OWNED_BY = SYS_ID
    # ------------------------------------------------------------------
    if not user_df.empty:
        merged = sim_df.merge(
            user_df,
            left_on="OWNED_BY",
            right_on="SYS_ID",
            how="left",
            suffixes=("", "_user"),
        )
    else:
        merged = sim_df.copy()
        for col in [
            "SYS_ID",
            "EMAIL",
            "NAME",
            "FIRST_NAME",
            "LAST_NAME",
            "ACTIVE",
            "DV_DEPARTMENT",
            "DV_COMPANY_user",
            "DV_TITLE",
        ]:
            merged[col] = None

    # ------------------------------------------------------------------
    # 4. Normalize phone numbers
    # Use U_COUNTRY (per row) to pick the correct region so that numbers
    # without a leading '+' are interpreted correctly (e.g. Brazilian
    # numbers stored as '5511...' must use region='BR' not 'US').
    # ------------------------------------------------------------------
    logger.info("[DATABRICKS] Normalizing phone numbers …")
    # Log raw MOBILE_NUMBER samples and format distribution BEFORE normalization
    raw_samples = merged["MOBILE_NUMBER"].dropna().head(15).tolist()
    logger.info("[DATABRICKS] RAW MOBILE_NUMBER samples (before normalization): %s", raw_samples)
    import re as _re
    _has_plus  = merged["MOBILE_NUMBER"].dropna().apply(lambda x: str(x).startswith("+")).sum()
    _has_55    = merged["MOBILE_NUMBER"].dropna().apply(lambda x: str(x).startswith("55") and not str(x).startswith("+")).sum()
    _has_plus55= merged["MOBILE_NUMBER"].dropna().apply(lambda x: str(x).startswith("+55")).sum()
    _other     = len(merged["MOBILE_NUMBER"].dropna()) - _has_plus - _has_55
    logger.info(
        "[DATABRICKS] RAW format breakdown — with '+': %d | starts '55' (no +): %d | starts '+55': %d | other: %d",
        _has_plus, _has_55, _has_plus55, _other
    )
    _len_dist = merged["MOBILE_NUMBER"].dropna().apply(lambda x: len(str(x))).value_counts().sort_index().to_dict()
    logger.info("[DATABRICKS] RAW MOBILE_NUMBER length distribution: %s", _len_dist)

    def _normalize_employee_phone(row):
        raw = row["MOBILE_NUMBER"]
        if not pd.notna(raw):
            return None
        u_country = str(row.get("U_COUNTRY", "") or "").strip()
        region = country_to_region(u_country) or "US"
        return normalize_phone(str(raw), region)

    merged["phone_number_normalized"] = merged.apply(_normalize_employee_phone, axis=1)
    logger.info(
        "[DATABRICKS] Sample regions used: %s",
        merged["U_COUNTRY"].value_counts().head(5).to_dict()
    )

    # Drop rows where normalization failed (very rare — only truly garbage data)
    before = len(merged)
    merged = merged.dropna(subset=["phone_number_normalized"])
    logger.info(
        f"[DATABRICKS] Dropped {before - len(merged)} rows with unparseable phone numbers"
    )

    # ------------------------------------------------------------------
    # 5. Create legacy-compatible columns for Phase 3
    # ------------------------------------------------------------------
    # "Wireless number" is what generate_reports_tool.py & analysis_engine.py use
    merged["Wireless number"] = merged["phone_number_normalized"]

    # Map Databricks active/install status → legacy column names
    def _derive_wireless_status(row):
        u_active = str(row.get("U_ACTIVE", "")).strip().lower()
        install = str(row.get("DV_INSTALL_STATUS", "")).strip().lower()
        if u_active == "false" or install == "retired":
            return "suspended"
        return "active"

    def _derive_account_status(row):
        u_active = str(row.get("U_ACTIVE", "")).strip().lower()
        if u_active == "false":
            return "inactive"
        return "active"

    merged["Wireless number status"] = merged.apply(_derive_wireless_status, axis=1)
    merged["Account status indicator"] = merged.apply(_derive_account_status, axis=1)

    # Friendly name columns
    merged["User first name"] = merged.get("FIRST_NAME", merged.get("DV_OWNED_BY"))
    merged["User last name"] = merged.get("LAST_NAME", pd.Series([""] * len(merged)))

    logger.info(
        f"[DATABRICKS] Final employee dataframe: {len(merged)} rows, {len(merged.columns)} columns"
    )
    return merged


# ============================================================================
# TOOL REGISTRATION
# ============================================================================


@tool_registry.register(
    name="load_databricks_employee_data",
    description=(
        "Connect to Databricks SQL warehouse and load employee/SIM card data from "
        "ServiceNow tables (snow_cmdb_ci_sim_card_view + snow_sys_user_view). "
        "Replaces manual CSV upload. Data is joined, phone numbers are normalized, "
        "and loaded into the in-memory SQLite 'Employee_data' table."
    ),
    tags=["databricks", "employee", "database", "servicenow"],
    requires_context=True,
)
def load_databricks_employee_data(
    country_filter: Annotated[
        Optional[str],
        Field(
            description="Optional ISO country name to filter SIM records (e.g. 'United States'). Leave empty to load all countries."
        ),
    ] = None,
) -> str:
    """
    Load employee data from Databricks into SQLite for Phase 3 analysis.

    This tool:
      1. Connects to Databricks SQL warehouse using PAT from env vars
      2. Queries snow_cmdb_ci_sim_card_view (phones + ownership + active status)
      3. Queries snow_sys_user_view (email, name, department)
      4. Joins on SYS_ID
      5. Normalizes MOBILE_NUMBER → digits-only national number
      6. Loads into 'Employee_data' in session SQLite

    Returns:
        JSON with success, employee_records, columns, etc.
    """
    logger.info("[TOOL] load_databricks_employee_data CALLED")

    try:
        session_id = get_current_session_id()
        if not session_id:
            return json.dumps({"success": False, "error": "No active session ID"})

        # Build the combined employee dataframe
        employee_df = _build_employee_dataframe(country_filter=country_filter)

        if employee_df.empty:
            return json.dumps(
                {
                    "success": False,
                    "error": "No employee records returned from Databricks",
                    "message": "Query returned 0 rows. Check DATABRICKS_TOKEN and table permissions.",
                }
            )

        # Store in SQLite
        table_name = "Employee_data"
        if drop_table_if_exists(session_id, table_name):
            logger.info(f"Dropped existing table '{table_name}' before refresh")

        _store_dataframe(session_id, table_name, employee_df)
        logger.info(f"Stored {len(employee_df)} rows in SQLite as '{table_name}'")

        result = {
            "success": True,
            "employee_table": table_name,
            "employee_records": len(employee_df),
            "databricks_source": True,
            "columns": list(employee_df.columns),
            "message": f"Successfully loaded {len(employee_df)} employee records from Databricks.",
        }

        logger.info(
            f"[TOOL] load_databricks_employee_data SUCCESS: {result['message']}"
        )
        return json.dumps(result)

    except Exception as e:
        logger.error(f"[TOOL] load_databricks_employee_data ERROR: {e}", exc_info=True)
        return json.dumps(
            {
                "success": False,
                "error": str(e),
                "message": f"Failed to load Databricks data: {e}",
            }
        )
