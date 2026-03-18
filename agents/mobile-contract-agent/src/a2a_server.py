"""
Mobile Contract Agent - A2A Server.

This module provides an A2A (Agent-to-Agent) protocol server for the Mobile Contract
analysis agent, enabling integration with other AI agents and systems.

The server provides access to AgenticAI SDK tools:
- DataFrame tools: list_available_files, upload, query, describe, execute_sql_query
- Calculator tools: calculator, calculate_expression, calculate_statistics
- Custom tools: invoice_pdf_to_tables

Skills are automatically registered from the config.yaml configuration.
"""

import logging
import os
from typing import Optional

# Import AgenticAI SDK
from agenticai.a2a import A2AFactory
from fastapi import APIRouter
from pydantic import BaseModel

# Import local tools
try:
    from . import tools  # noqa: F401
    from .file_upload_api import create_upload_api
except ImportError:
    import tools  # noqa: F401
    from file_upload_api import create_upload_api

logger = logging.getLogger(__name__)


# ── Databricks REST endpoints (called from the UI) ──────────────────────────


class DatabricksTestRequest(BaseModel):
    token: str
    host: Optional[str] = None
    http_path: Optional[str] = None
    catalog: Optional[str] = None
    schema_name: Optional[str] = None  # 'schema' is a Pydantic reserved name


class DatabricksFetchRequest(BaseModel):
    token: str
    host: Optional[str] = None
    http_path: Optional[str] = None
    catalog: Optional[str] = None
    schema_name: Optional[str] = None
    country_filter: Optional[str] = None


_DB_DEFAULTS = {
    "host": "adb-4071335540424391.11.azuredatabricks.net",
    "http_path": "/sql/1.0/warehouses/916c447fdd11cd1e",
    "catalog": "efdataonelh_prd",
    "schema": "generaldiscovery_servicenow_r",
}

databricks_router = APIRouter(prefix="/databricks", tags=["databricks"])


@databricks_router.get("/ping")
async def ping_databricks_connection():
    """
    Test Databricks connectivity using env-var credentials only.
    No token required from the UI — reads DATABRICKS_TOKEN from .env.
    Called by the simple 'Connect to Databricks' button in the UI.
    """
    try:
        from databricks import sql as databricks_sql
    except ImportError:
        return {
            "success": False,
            "message": "databricks-sql-connector is not installed",
        }

    host = os.environ.get("DATABRICKS_HOST", _DB_DEFAULTS["host"])
    http_path = os.environ.get("DATABRICKS_HTTP_PATH", _DB_DEFAULTS["http_path"])
    token = os.environ.get("DATABRICKS_TOKEN", "")
    catalog = os.environ.get("DATABRICKS_CATALOG", _DB_DEFAULTS["catalog"])

    if not token:
        return {
            "success": False,
            "message": "DATABRICKS_TOKEN is not configured on the server",
        }

    try:
        conn = databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
            catalog=catalog,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"success": True, "message": "Connected to Databricks successfully"}
    except Exception as e:
        logger.warning(f"Databricks ping failed: {e}")
        return {"success": False, "message": str(e)}


@databricks_router.post("/test")
async def test_databricks_connection(req: DatabricksTestRequest):
    """Test connectivity to Databricks SQL warehouse with SELECT 1."""
    try:
        from databricks import sql as databricks_sql
    except ImportError:
        return {
            "success": False,
            "message": "databricks-sql-connector is not installed",
        }

    host = req.host or os.environ.get("DATABRICKS_HOST", _DB_DEFAULTS["host"])
    http_path = req.http_path or os.environ.get(
        "DATABRICKS_HTTP_PATH", _DB_DEFAULTS["http_path"]
    )
    catalog = req.catalog or os.environ.get(
        "DATABRICKS_CATALOG", _DB_DEFAULTS["catalog"]
    )
    token = req.token

    try:
        conn = databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
            catalog=catalog,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        return {"success": True, "message": "Connected successfully"}
    except Exception as e:
        logger.warning(f"Databricks test-connection failed: {e}")
        return {"success": False, "message": str(e)}


@databricks_router.post("/fetch-employees")
async def fetch_databricks_employees(req: DatabricksFetchRequest):
    """Fetch employee/SIM data from Databricks and return record count."""
    try:
        from databricks import sql as databricks_sql
    except ImportError:
        return {
            "success": False,
            "message": "databricks-sql-connector is not installed",
        }

    host = req.host or os.environ.get("DATABRICKS_HOST", _DB_DEFAULTS["host"])
    http_path = req.http_path or os.environ.get(
        "DATABRICKS_HTTP_PATH", _DB_DEFAULTS["http_path"]
    )
    catalog = req.catalog or os.environ.get(
        "DATABRICKS_CATALOG", _DB_DEFAULTS["catalog"]
    )
    schema = req.schema_name or os.environ.get(
        "DATABRICKS_SCHEMA", _DB_DEFAULTS["schema"]
    )
    token = req.token

    try:
        conn = databricks_sql.connect(
            server_hostname=host,
            http_path=http_path,
            access_token=token,
            catalog=catalog,
            schema=schema,
        )
        cursor = conn.cursor()

        # Count SIM card records (optionally filtered by country)
        count_sql = f"SELECT COUNT(*) AS cnt FROM snow_cmdb_ci_sim_card_view"
        if req.country_filter:
            count_sql += f" WHERE U_COUNTRY = '{req.country_filter}'"

        cursor.execute(count_sql)
        row = cursor.fetchone()
        record_count = row[0] if row else 0

        cursor.close()
        conn.close()
        return {"success": True, "record_count": record_count}
    except Exception as e:
        logger.warning(f"Databricks fetch-employees failed: {e}")
        return {"success": False, "message": str(e), "record_count": 0}


def main():
    """
    Start the A2A server with integrated file upload API.

    All configuration is loaded from the config file specified by the CONFIG_PATH
    environment variable, or defaults to config.yaml if not set.

    Supports debugpy for VS Code debugging when DEBUGPY_ENABLE=true environment variable is set.
    """
    # Check if debugger should be enabled
    if os.environ.get("DEBUGPY_ENABLE", "").lower() == "true":
        try:
            import debugpy

            debugpy.listen(("0.0.0.0", 5678))
            print("Debugger enabled - listening on port 5678")

            # Only wait for client if DEBUGPY_WAIT is set (Docker mode)
            if os.environ.get("DEBUGPY_WAIT", "").lower() == "true":
                print("   Waiting for VS Code debugger to attach...")
                debugpy.wait_for_client()
                print("Debugger attached!")
            else:
                print("   Server starting - attach debugger when ready")
        except ImportError:
            print("WARNING: debugpy not installed - continuing without debugger")
        except Exception as e:
            print(f"WARNING: Failed to start debugger: {e}")

    # Create A2A server
    factory = A2AFactory()
    server = factory.create_server()

    # Mount file upload API routes to the main FastAPI app
    upload_app = create_upload_api()

    # Mount all routes from upload_app to the main app
    for route in upload_app.routes:
        server.fastapi_app.routes.append(route)

    # Mount Databricks test/fetch endpoints
    server.fastapi_app.include_router(databricks_router)

    print("[OK] File upload API mounted on main server (port 8000)")
    print("  Legacy upload endpoint: http://localhost:8000/upload")
    print("  Signed URL endpoint: http://localhost:8000/upload/url")
    print(
        "  Direct upload endpoint: http://localhost:8000/upload/direct/{job_id}/pdf/{filename}?token=..."
    )
    print("  Upload complete endpoint: http://localhost:8000/upload/complete")
    print("  Manual orchestrator trigger: http://localhost:8000/orchestrator/trigger")
    print("  Databricks ping (env vars): http://localhost:8000/databricks/ping")
    print("  Databricks test (token): http://localhost:8000/databricks/test")
    print("  Databricks fetch: http://localhost:8000/databricks/fetch-employees")
    print("  Job status endpoint: http://localhost:8000/jobs/{job_id}")
    print("  Cleanup uploads: DELETE http://localhost:8000/cleanup/{job_id}")
    print(
        "  Employee filtered CSV: http://localhost:8000/output/employee-only-filtered?country=Germany"
    )
    print("  Max upload size: 200 MB")

    # Run the server
    server.run()


if __name__ == "__main__":
    main()
