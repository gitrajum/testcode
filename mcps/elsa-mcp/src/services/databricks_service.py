"""
Databricks Service - ELSA UC3 Data Connection
Provides MCP tools to query CMDB / ServiceNow data from Elsa Databricks.
"""

import logging
from contextlib import contextmanager
from typing import Any, Optional

from databricks import sql as databricks_sql
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from ..config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


@contextmanager
def _get_connection():
    """Open a short-lived Databricks SQL connection and close it when done."""
    settings = get_settings()

    kwargs: dict[str, Any] = {
        "server_hostname": settings.databricks_server_hostname,
        "http_path": settings.databricks_http_path,
        "access_token": settings.databricks_access_token,
        "catalog": settings.databricks_catalog,
        "schema": settings.databricks_schema,
    }

    if settings.databricks_use_proxy and settings.databricks_proxy_host:
        kwargs["_use_proxy"] = True
        kwargs["_proxy_host"] = settings.databricks_proxy_host
        kwargs["_proxy_port"] = settings.databricks_proxy_port

    conn = databricks_sql.connect(**kwargs)
    try:
        yield conn
    finally:
        conn.close()


def _rows_to_dicts(cursor) -> list[dict[str, Any]]:
    """Convert cursor rows to a list of column-name-keyed dicts."""
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _build_ci_filter(column: str, ci_item: Optional[str]) -> str:
    """
    Build a SQL WHERE fragment for one or more CI items.

    Accepts a single name or a semicolon-separated list, e.g.
    ``"SERVER-A;SERVER-B;SERVER-C"``.  Each token is matched with LIKE
    (partial, case-insensitive) and the tokens are combined with OR.
    Returns an empty string when ci_item is None or blank.
    """
    if not ci_item:
        return ""
    tokens = [t.strip() for t in ci_item.split(";") if t.strip()]
    if not tokens:
        return ""
    conditions = " or ".join(
        f"lower({column}) like lower('%{token}%')" for token in tokens
    )
    return f"and ({conditions})"


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------


def register_databricks_tools(mcp: FastMCP):
    """Register all Databricks / ELSA tools with the MCP server."""

    # ------------------------------------------------------------------
    # 1. Change requests for CI items
    # ------------------------------------------------------------------
    @mcp.tool()
    async def get_change_requests(
        ci_item: Optional[str] = None,
        since_date: str = "2025-01-01",
        exclude_standard: bool = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Retrieve ServiceNow change requests (CHG) linked to server CI items.

        Joins snow_task_ci_view with snow_change_request_view and
        snow_cmdb_ci_server_view to return only server-related changes.

        Args:
            ci_item:          Optional CI item name filter. Supports a semicolon-separated
                              list for multiple CIs, e.g. ``"SERVER-A;SERVER-B;SERVER-C"``.
                              Each token is matched with a case-insensitive LIKE (partial match).
            since_date:       Only return records created on or after this date (YYYY-MM-DD).
            exclude_standard: When True (default), filters out changes with DV_TYPE = 'Standard'.
            limit:            Maximum number of rows to return (default 500).

        Returns:
            List of dicts with keys: dv_ci_item, dv_task, start_date, end_date,
            dv_category, dv_type.
        """
        logger.info(
            f"get_change_requests called: ci_item={ci_item}, since={since_date}, exclude_standard={exclude_standard}"
        )

        ci_filter = _build_ci_filter("t.DV_CI_ITEM", ci_item)
        standard_filter = "and DV_TYPE != 'Standard'" if exclude_standard else ""

        query = f"""
            select lower(t.DV_CI_ITEM)  as dv_ci_item,
                   t.DV_TASK            as dv_task,
                   c.START_DATE         as start_date,
                   c.END_DATE           as end_date,
                   c.DV_CATEGORY        as dv_category,
                   c.DV_TYPE            as dv_type
            from snow_task_ci_view t
            left join efdataonelh_prd.generaldiscovery_servicenow_r.snow_change_request_view c
              on t.TASK = c.SYS_ID
            left join snow_cmdb_ci_server_view s
              on t.CI_ITEM = s.SYS_ID
            where t.DV_TASK like 'CHG%'
              and t.SYS_CREATED_ON >= '{since_date}'
              and s.SYS_ID is not NULL
              {standard_filter}
              {ci_filter}
            order by dv_ci_item ASC, start_date DESC
            limit {limit}
        """

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return _rows_to_dicts(cursor)
        except Exception as exc:
            logger.error(f"get_change_requests failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 2. Incidents for CI items
    # ------------------------------------------------------------------
    @mcp.tool()
    async def get_incidents(
        ci_item: Optional[str] = None,
        since_date: str = "2025-01-01",
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """
        Retrieve ServiceNow incidents (INC) linked to server CI items.

        Joins snow_task_ci_view with snow_incident_view and
        snow_cmdb_ci_server_view, excluding Event Monitoring contacts.

        Args:
            ci_item:    Optional CI item name filter. Supports a semicolon-separated
                        list for multiple CIs, e.g. ``"SERVER-A;SERVER-B;SERVER-C"``.
                        Each token is matched with a case-insensitive LIKE (partial match).
            since_date: Only return records created on or after this date (YYYY-MM-DD).
            limit:      Maximum number of rows to return (default 500).

        Returns:
            List of dicts with keys: dv_ci_item, dv_task, opened_at,
            dv_incident_state, dv_close_code, dv_contact_type.
        """
        logger.info(f"get_incidents called: ci_item={ci_item}, since={since_date}")

        ci_filter = _build_ci_filter("t.DV_CI_ITEM", ci_item)

        query = f"""
            select lower(t.DV_CI_ITEM)  as dv_ci_item,
                   t.DV_TASK            as dv_task,
                   i.OPENED_AT          as opened_at,
                   i.DV_INCIDENT_STATE  as dv_incident_state,
                   i.DV_CLOSE_CODE      as dv_close_code,
                   i.DV_CONTACT_TYPE    as dv_contact_type
            from snow_task_ci_view t
            left join efdataonelh_prd.generaldiscovery_servicenow_r.snow_incident_view i
              on t.TASK = i.SYS_ID
            left join snow_cmdb_ci_server_view s
              on t.CI_ITEM = s.SYS_ID
            where t.DV_TASK like 'INC%'
              and t.SYS_CREATED_ON >= '{since_date}'
              and s.SYS_ID is not NULL
              and DV_CONTACT_TYPE != 'Event Monitoring'
              {ci_filter}
            order by dv_ci_item ASC, opened_at DESC
            limit {limit}
        """

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return _rows_to_dicts(cursor)
        except Exception as exc:
            logger.error(f"get_incidents failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 3. Application / Server inventory
    # ------------------------------------------------------------------
    @mcp.tool()
    async def get_app_server_inventory(
        app_name: Optional[str] = None,
        server_name: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Retrieve the EA CMDB app-to-server inventory from ELSA.

        Combines business applications (via BeatID) and patterns linked to
        server records. Deduplicates via UNION.

        Args:
            app_name:    Optional app name filter (LIKE match).
            server_name: Optional server name filter (LIKE match).
            limit:       Maximum rows to return (default 1000).

        Returns:
            List of dicts with keys: app_name, app_sys_class_name, app_beatid,
            internal_lifecycle, dv_business_criticality, appsvc_name,
            server_name, server_sys_class_name, server_dv_install_status,
            server_dv_used_for.
        """
        logger.info(f"get_app_server_inventory: app={app_name}, server={server_name}")

        app_filter = (
            f"and lower(i.APP_NAME) like lower('%{app_name}%')" if app_name else ""
        )
        srv_filter = (
            f"and lower(i.SERVER_NAME) like lower('%{server_name}%')"
            if server_name
            else ""
        )

        query = f"""
            select distinct
                   i.APP_NAME                    as app_name,
                   i.APP_SYS_CLASS_NAME          as app_sys_class_name,
                   b.NUMBER                      as app_beatid,
                   b.INTERNAL_LIFECYCLE          as internal_lifecycle,
                   b.DV_BUSINESS_CRITICALITY     as dv_business_criticality,
                   i.APPSVC_NAME                 as appsvc_name,
                   i.SERVER_NAME                 as server_name,
                   i.SERVER_SYS_CLASS_NAME       as server_sys_class_name,
                   i.SERVER_DV_INSTALL_STATUS    as server_dv_install_status,
                   s.DV_U_USED_FOR               as server_dv_used_for
            from snow_ea_cmdb_inventory_view_001 i
            left join snow_x_inpgh_upmx_business_application_view b on i.APP_SYS_ID = b.SYS_ID
            left join snow_cmdb_ci_server_view s on i.SERVER_SYS_ID = s.SYS_ID
            where b.SYS_ID is not NULL and s.SYS_ID is not NULL
              {app_filter} {srv_filter}

            union

            select distinct
                   i.APP_NAME,
                   i.APP_SYS_CLASS_NAME,
                   p.NUMBER                      as app_beatid,
                   p.INTERNAL_LIFECYCLE,
                   p.DV_BUSINESS_CRITICALITY,
                   i.APPSVC_NAME,
                   i.SERVER_NAME,
                   i.SERVER_SYS_CLASS_NAME,
                   i.SERVER_DV_INSTALL_STATUS,
                   s.DV_U_USED_FOR               as server_dv_used_for
            from snow_ea_cmdb_inventory_view_001 i
            left join snow_x_inpgh_upmx_pattern_view p on i.APP_SYS_ID = p.SYS_ID
            left join snow_cmdb_ci_server_view s on i.SERVER_SYS_ID = s.SYS_ID
            where p.SYS_ID is not NULL and s.SYS_ID is not NULL
              {app_filter} {srv_filter}

            limit {limit}
        """

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return _rows_to_dicts(cursor)
        except Exception as exc:
            logger.error(f"get_app_server_inventory failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 4. Active servers
    # ------------------------------------------------------------------
    @mcp.tool()
    async def get_active_servers(
        used_for: Optional[str] = None,
        name_filter: Optional[str] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Retrieve all active servers from snow_cmdb_ci_server_view.

        Args:
            used_for:    Optional filter on DV_U_USED_FOR field (LIKE match).
            name_filter: Optional filter on server NAME (LIKE match).
            limit:       Maximum rows to return (default 1000).

        Returns:
            List of dicts with keys: name, dv_install_status,
            dv_u_used_for, short_description.
        """
        logger.info(f"get_active_servers: used_for={used_for}, name={name_filter}")

        used_for_filter = (
            f"and lower(DV_U_USED_FOR) like lower('%{used_for}%')" if used_for else ""
        )
        name_f = f"and lower(NAME) like lower('%{name_filter}%')" if name_filter else ""

        query = f"""
            select NAME             as name,
                   DV_INSTALL_STATUS as dv_install_status,
                   DV_U_USED_FOR    as dv_u_used_for,
                   SHORT_DESCRIPTION as short_description
            from snow_cmdb_ci_server_view
            where U_ACTIVE = true
              {used_for_filter}
              {name_f}
            limit {limit}
        """

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    return _rows_to_dicts(cursor)
        except Exception as exc:
            logger.error(f"get_active_servers failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 5. Server decommission summary (app inventory + CHG/INC counts)
    # ------------------------------------------------------------------
    @mcp.tool()
    async def get_server_decommission_summary(
        server_name: Optional[str] = None,
        since_date: str = "2025-01-01",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """
        Retrieve a decommission-readiness summary per server: linked business
        applications/patterns, lifecycle and criticality metadata, whether the
        server is shared or dedicated, and the number of change requests (CHG)
        and incidents (INC) since a given date.

        Args:
            server_name: Optional server name filter. Supports a
                         semicolon-separated list for multiple servers, e.g.
                         ``"SERVER-A;SERVER-B;SERVER-C"``. Each token is
                         matched with a case-insensitive LIKE (partial match).
            since_date:  Count CHG/INC records created on or after this date
                         (YYYY-MM-DD, default ``"2025-01-01"``).
            limit:       Maximum rows to return (default 1000).

        Returns:
            List of dicts with keys: app_beatid, app_name, app_sys_class_name,
            internal_lifecycle, dv_business_criticality, server_name,
            server_sys_class_name, server_dv_install_status,
            server_dv_used_for, server_short_description, scope,
            chg_tasks, inc_tasks.
        """
        logger.info(
            f"get_server_decommission_summary: server={server_name}, since={since_date}"
        )

        server_filter = _build_ci_filter("i.SERVER_NAME", server_name)

        query = f"""
            select distinct
                   b.NUMBER                      AS app_beatid,
                   i.APP_NAME                    AS app_name,
                   i.APP_SYS_CLASS_NAME          AS app_sys_class_name,
                   b.INTERNAL_LIFECYCLE          AS internal_lifecycle,
                   b.DV_BUSINESS_CRITICALITY     AS dv_business_criticality,
                   upper(i.SERVER_NAME)          AS server_name,
                   i.SERVER_SYS_CLASS_NAME       AS server_sys_class_name,
                   i.SERVER_DV_INSTALL_STATUS    AS server_dv_install_status,
                   s.DV_U_USED_FOR               AS server_dv_used_for,
                   s.SHORT_DESCRIPTION           AS server_short_description,
                   CASE WHEN i2.APP_COUNT > 1 THEN 'Shared' ELSE 'Dedicated' END AS scope,
                   CASE WHEN t.CHG_TASKS IS NULL THEN 0 ELSE t.CHG_TASKS END AS chg_tasks,
                   CASE WHEN t.INC_TASKS IS NULL THEN 0 ELSE t.INC_TASKS END AS inc_tasks

            from snow_ea_cmdb_inventory_view_001 i

            left join snow_cmdb_ci_server_view s
              on i.SERVER_SYS_ID = s.SYS_ID

            left join (
                select distinct SYS_ID, NUMBER, NAME, INTERNAL_LIFECYCLE,
                       DV_BUSINESS_CRITICALITY, DV_ALIAS, SHORT_DESCRIPTION
                from snow_x_inpgh_upmx_business_application_view
                union
                select distinct SYS_ID, NUMBER, NAME, INTERNAL_LIFECYCLE,
                       DV_BUSINESS_CRITICALITY, DV_ALIAS, SHORT_DESCRIPTION
                from snow_x_inpgh_upmx_pattern_view
            ) b ON i.APP_SYS_ID = b.SYS_ID

            left join (
                select SERVER_SYS_ID, count(distinct APP_SYS_ID) AS APP_COUNT
                from snow_ea_cmdb_inventory_view_001
                where SERVER_SYS_ID is not NULL and APP_SYS_ID is not NULL
                group by SERVER_SYS_ID
            ) i2 on i.SERVER_SYS_ID = i2.SERVER_SYS_ID

            left join (
                select upper(s2.NAME) AS SERVER_NAME,
                       count(distinct t1.DV_TASK) AS CHG_TASKS,
                       count(distinct t2.TASK)    AS INC_TASKS
                from snow_cmdb_ci_server_view s2
                left join snow_task_ci_view t1
                  on s2.SYS_ID = t1.CI_ITEM
                  and t1.DV_TASK like 'CHG%'
                  and t1.SYS_CREATED_ON >= '{since_date}'
                left join snow_change_request_view c
                  on t1.TASK = c.SYS_ID
                  and c.DV_TYPE not like 'Standard'
                left join snow_task_ci_view t2
                  on s2.SYS_ID = t2.CI_ITEM
                  and t2.DV_TASK like 'INC%'
                  and t2.SYS_CREATED_ON >= '{since_date}'
                left join snow_incident_view i3
                  on t2.TASK = i3.SYS_ID
                  and i3.DV_CONTACT_TYPE not like 'Event Monitoring'
                where s2.U_ACTIVE = true
                  and c.SYS_ID is not NULL
                  and i3.SYS_ID is not NULL
                  and t1.SYS_ID is not NULL
                  and t2.SYS_ID is not NULL
                group by s2.NAME
            ) t on i.SERVER_NAME = t.SERVER_NAME

            where b.SYS_ID is not NULL
              and s.SYS_ID is not NULL
              {server_filter}

            limit {limit}
        """

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(query)
                    rows = _rows_to_dicts(cursor)

            # Deduplicate by server_name, keeping only the first occurrence
            seen_servers: set[str] = set()
            unique_rows = []
            for row in rows:
                srv = row.get("server_name")
                if srv not in seen_servers:
                    seen_servers.add(srv)
                    unique_rows.append(row)
            rows = unique_rows

            if not return_as_file:
                return rows

            # Encode as CSV so the SDK intercepts content_base64, saves the
            # file to session context, and returns only metadata to the LLM.
            import base64
            import csv
            import io

            if not rows:
                return {
                    "name": "elsa_server_data.csv",
                    "content_base64": "",
                    "size": 0,
                    "mime_type": "text/csv",
                    "row_count": 0,
                    "message": "No rows returned for the given server filter.",
                }

            buf = io.StringIO()
            writer = csv.DictWriter(
                buf, fieldnames=list(rows[0].keys()), lineterminator="\n"
            )
            writer.writeheader()
            writer.writerows(rows)
            csv_bytes = buf.getvalue().encode("utf-8")

            logger.info(
                f"get_server_decommission_summary: returning {len(rows)} rows as CSV file "
                f"({len(csv_bytes):,} bytes) — SDK will auto-save to session context"
            )

            return {
                "name": "elsa_server_data.csv",
                "content_base64": base64.b64encode(csv_bytes).decode("ascii"),
                "size": len(csv_bytes),
                "mime_type": "text/csv",
                "row_count": len(rows),
            }

        except Exception as exc:
            logger.error(f"get_server_decommission_summary failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    # ------------------------------------------------------------------
    # 6. Generic SQL execution (power-user escape hatch)
    # ------------------------------------------------------------------
    @mcp.tool()
    async def execute_sql(
        query: str,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """
        Execute an arbitrary read-only SQL SELECT query against Elsa Databricks.

        A LIMIT clause is automatically appended if not already present to
        prevent accidental full-table scans.

        Args:
            query: A SQL SELECT statement to execute.
            limit: Safety row limit appended when the query has no LIMIT
                   clause (default 200).

        Returns:
            List of dicts representing the result rows.
        """
        if not query.strip().upper().startswith("SELECT"):
            raise ToolError("Only SELECT statements are allowed.")

        safe_query = query.rstrip().rstrip(";")
        if "limit" not in safe_query.lower():
            safe_query = f"{safe_query}\nLIMIT {limit}"

        logger.info(f"execute_sql: {safe_query[:200]}")

        try:
            with _get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(safe_query)
                    return _rows_to_dicts(cursor)
        except Exception as exc:
            logger.error(f"execute_sql failed: {exc}")
            raise ToolError(f"Databricks query failed: {exc}") from exc

    logger.info(
        "Databricks (ELSA) tools registered: get_change_requests, get_incidents, get_app_server_inventory, get_active_servers, get_server_decommission_summary, execute_sql"
    )
