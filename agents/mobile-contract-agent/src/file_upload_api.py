"""
File upload API endpoint for handling large file uploads.

This module provides a FastAPI endpoint for uploading large files (e.g., PDFs)
that bypasses the JSON-RPC payload size limit.

File Upload Strategy:
1. Frontend requests signed URL from backend
2. Backend creates job record in Azure Table Storage
3. Browser uploads directly to storage using signed URL (easily migrates to Azure Blob)
4. Frontend notifies backend after upload completion
5. Backend triggers phased orchestrator

File size limit: 200 MB
Storage: Local disk (uploads/{job_id}/{file_type}/) - Azure Blob Storage ready
Database: Azure Table Storage (survives container restarts and scale-out)
"""

import io
import json
import logging
import os
import re
import secrets
import shutil
import time
import uuid
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import httpx
from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Silence the general azure-core and tables loggers
logging.getLogger("azure.core").setLevel(logging.WARNING)
logging.getLogger("azure.data.tables").setLevel(logging.WARNING)

# Maximum file size: 200 MB
MAX_UPLOAD_SIZE = 200 * 1024 * 1024  # 200 MB in bytes


# ============================================================================
# SECURITY — PATH VALIDATION
# ============================================================================


def _validate_uuid(value: str, param_name: str = "parameter") -> str:
    """
    Validate that a string is a valid UUID v4 format.
    
    Prevents path traversal attacks by ensuring job_id/session_id cannot
    contain directory traversal characters like '../'.
    
    Args:
        value: The string to validate as a UUID
        param_name: Name of the parameter for error messages
        
    Returns:
        The validated UUID string
        
    Raises:
        ValueError: If the value is not a valid UUID
    """
    try:
        # This will raise ValueError if not a valid UUID
        uuid.UUID(value)
        return value
    except ValueError:
        raise ValueError(
            f"Invalid {param_name}: must be a valid UUID format (received: {value!r})"
        )


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent path traversal attacks.
    
    Removes any directory components and path traversal sequences.
    
    Args:
        filename: The filename to sanitize
        
    Returns:
        Sanitized filename with only the basename (no path components)
    """
    # Get just the basename, removing any path components
    safe_name = Path(filename).name
    
    # Additional check: reject if it still contains suspicious patterns
    if ".." in safe_name or "/" in safe_name or "\\" in safe_name:
        raise ValueError(f"Invalid filename: contains path traversal characters: {filename!r}")
    
    return safe_name


def _validate_path_within_base(file_path: Path, base_dir: Path, context: str = "file") -> Path:
    """
    Validate that a resolved file path is within the expected base directory.
    
    Prevents path traversal attacks by ensuring the final resolved path
    doesn't escape the intended directory.
    
    Args:
        file_path: The path to validate
        base_dir: The base directory that must contain the file_path
        context: Description of what's being validated (for error messages)
        
    Returns:
        The validated path
        
    Raises:
        ValueError: If the path is outside the base directory
    """
    resolved_path = file_path.resolve()
    resolved_base = base_dir.resolve()
    
    # Use is_relative_to if available (Python 3.9+), otherwise use string comparison
    try:
        if not resolved_path.is_relative_to(resolved_base):
            raise ValueError(
                f"Access denied: {context} path escapes base directory (path: {file_path}, base: {base_dir})"
            )
    except AttributeError:
        # Fallback for Python < 3.9
        if not str(resolved_path).startswith(str(resolved_base)):
            raise ValueError(
                f"Access denied: {context} path escapes base directory (path: {file_path}, base: {base_dir})"
            )
    
    return file_path


# Use persistent volume for uploads, data, and output
UPLOAD_DIR = Path("/mnt/agentfiles/uploads")
DATA_DIR = Path("/mnt/agentfiles/data")
OUTPUT_DIR = Path("/mnt/agentfiles/output")

# Create directories with error handling to prevent startup crashes
try:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"✓ Directories created successfully")
except PermissionError as e:
    logger.error(f"❌ Permission denied creating directories in /mnt/agentfiles: {e}")
    logger.error(f"   The Azure File Share may not have write permissions for user {os.getuid()}")
    logger.error(f"   App will continue but file uploads may fail")
except Exception as e:
    logger.error(f"❌ Failed to create directories: {e}")
    logger.error(f"   App will continue but file uploads may fail")

# Azure Table Storage table names for job tracking
# Auth: AZURE_STORAGE_CONNECTION_STRING  OR
#       AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY
JOB_TABLE_NAME  = os.getenv("JOB_TABLE_NAME",  "jobtracker")
FILE_TABLE_NAME = os.getenv("FILE_TABLE_NAME", "filesmetadata")

logger.info(f"File upload directory: {UPLOAD_DIR}")
logger.info(f"Data directory: {DATA_DIR}")
logger.info(f"Output directory: {OUTPUT_DIR}")
logger.info(f"Job table: {JOB_TABLE_NAME} | File table: {FILE_TABLE_NAME}")

# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class StartJobRequest(BaseModel):
    user_id: Optional[str] = Field(None, description="User ID for tracking")


class SignedUrlRequest(BaseModel):
    job_id: str = Field(..., description="Job ID from /upload/job/start")
    filename: str = Field(..., description="Original filename to preserve extension")
    file_type: Optional[str] = Field(
        None, description="File type: pdf or csv (auto-detected if not provided)"
    )
    user_id: Optional[str] = Field(None, description="User requesting the upload")
    content_type: Optional[str] = Field(None, description="Optional MIME type hint")
    expires_in_seconds: int = Field(900, ge=60, le=3600, description="Signed URL TTL")


class UploadCompleteRequest(BaseModel):
    job_id: str
    success: bool = True
    uploaded_path: Optional[str] = Field(
        None, description="Path URL returned by frontend after upload"
    )
    trigger_orchestrator: bool = Field(
        True, description="Whether to trigger orchestrator after upload"
    )
    orchestrator_message: Optional[str] = Field(
        None, description="Custom message for orchestrator"
    )


# ============================================================================
# AZURE TABLE STORAGE — JOB TRACKING
# ============================================================================
#
# Two tables:
#   jobtracker   — PartitionKey="job"  RowKey=job_id
#   filesmetadata— PartitionKey=job_id  RowKey=file_id
#
# Auth (same pattern as AzureTableFingerprintStore in invoice_processor.py):
#   AZURE_STORAGE_CONNECTION_STRING
#   OR  AZURE_STORAGE_ACCOUNT_NAME + AZURE_STORAGE_ACCOUNT_KEY
# ============================================================================

def _make_table_client(table_name: str):
    """Return an Azure TableClient for the given table, creating it if needed."""
    from azure.data.tables import TableServiceClient  # type: ignore
    from azure.identity import DefaultAzureCredential  # type: ignore

    # Try connection string first (for local development/backwards compatibility)
    conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if conn_str:
        svc = TableServiceClient.from_connection_string(conn_str, logging_enable=False)
    else:
        # Use managed identity with DefaultAzureCredential (production/secure)
        account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
        if not account:
            raise EnvironmentError(
                "Job tracking requires AZURE_STORAGE_ACCOUNT_NAME environment variable"
            )
        credential = DefaultAzureCredential()
        svc = TableServiceClient(
            endpoint=f"https://{account}.table.core.windows.net",
            credential=credential,
            logging_enable=False,
        )
    svc.create_table_if_not_exists(table_name, logging_enable=False)
    return svc.get_table_client(table_name, logging_enable=False)


# Module-level lazy clients
_job_table_client  = None
_file_table_client = None


def _jobs() :
    global _job_table_client
    if _job_table_client is None:
        _job_table_client = _make_table_client(JOB_TABLE_NAME)
        logger.info(f"Job tracking: Azure Table Storage (table='{JOB_TABLE_NAME}')")
    return _job_table_client


def _files():
    global _file_table_client
    if _file_table_client is None:
        _file_table_client = _make_table_client(FILE_TABLE_NAME)
        logger.info(f"File tracking: Azure Table Storage (table='{FILE_TABLE_NAME}')")
    return _file_table_client


def _utcnow_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _get_job(job_id: str) -> Optional[Dict]:
    """Get job by ID."""
    try:
        entity = _jobs().get_entity(partition_key="job", row_key=job_id)
        return dict(entity)
    except Exception:
        return None


def _get_job_with_files(job_id: str) -> Optional[Dict]:
    """Get job with all associated file records."""
    job = _get_job(job_id)
    if not job:
        return None
    file_entities = _files().query_entities(f"PartitionKey eq '{job_id}'")
    job["files"] = [dict(f) for f in file_entities]
    return job


def _create_job(user_id: Optional[str] = None) -> Dict:
    """Create new job entry in Azure Table Storage."""
    job_id = str(uuid.uuid4())
    now = _utcnow_iso()
    entity = {
        "PartitionKey":  "job",
        "RowKey":        job_id,
        "user_id":       user_id or "",
        "status":        "PENDING",
        "current_phase": "UPLOADING",
        "created_at":    now,
        "updated_at":    now,
        "error_message": "",
        "phase_message": "Job created, waiting for files...",
        "results": "",
    }
    _jobs().create_entity(entity)
    logger.info(f"[JOB_CREATED] job_id={job_id} user_id={user_id}")
    return {
        "job_id":     job_id,
        "user_id":    user_id,
        "status":     "PENDING",
        "created_at": now,
    }


def _add_file_to_job(
    job_id: str,
    filename: str,
    file_type: str,
    expires_in_seconds: int = 900,
) -> Dict:
    """Add a file record to the job in Azure Table Storage."""
    # Security: Validate job_id is a proper UUID to prevent path traversal
    _validate_uuid(job_id, "job_id")
    
    file_id    = str(uuid.uuid4())
    token      = secrets.token_urlsafe(24)
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in_seconds)

    # Security: Sanitize filename to prevent path traversal
    safe_name      = _sanitize_filename(filename)
    safe_ext       = Path(safe_name).suffix
    saved_filename = safe_name if safe_ext else f"{safe_name}.bin"

    stored_relative = f"{job_id}/{file_type}/{saved_filename}"
    file_path       = UPLOAD_DIR / stored_relative
    
    # Security: Validate constructed path is within UPLOAD_DIR
    _validate_path_within_base(file_path, UPLOAD_DIR, "upload file")
    now             = _utcnow_iso()

    entity = {
        "PartitionKey":    job_id,
        "RowKey":          file_id,
        "job_id":          job_id,
        "file_type":       file_type,
        "file_url":        str(file_path),
        "original_name":   filename,
        "stored_relative": stored_relative,
        "upload_token":    token,
        "expires_at":      expires_at.isoformat() + "Z",
        "status":          "PENDING",
        "created_at":      now,
        "updated_at":      now,
        "size_bytes":      0,
        "error_message":   "",
    }
    _files().create_entity(entity)
    logger.info(f"[FILE_ADDED] file_id={file_id} job_id={job_id} type={file_type} name={filename}")
    return {
        "file_id":         file_id,
        "job_id":          job_id,
        "file_type":       file_type,
        "file_url":        str(file_path),
        "original_name":   filename,
        "stored_relative": stored_relative,
        "upload_token":    token,
        "expires_at":      expires_at.isoformat() + "Z",
        "status":          "PENDING",
    }


def _update_file_status(
    file_id: str,
    job_id: str,
    status: str,
    size_bytes: Optional[int] = None,
    error_message: Optional[str] = None,
) -> None:
    """Merge-update a file entity's status fields."""
    patch = {
        "PartitionKey": job_id,
        "RowKey":       file_id,
        "status":       status,
        "updated_at":   _utcnow_iso(),
        "error_message": error_message or "",
    }
    if size_bytes is not None:
        patch["size_bytes"] = size_bytes
    _files().update_entity(patch, mode="merge")


def update_job(job_id: str, **fields) -> None:
    """Merge-update arbitrary fields on a job entity."""
    if not fields:
        return
    patch = {"PartitionKey": "job", "RowKey": job_id, "updated_at": _utcnow_iso()}
    patch.update(fields)
    _jobs().update_entity(patch, mode="merge")


def _get_all_file_paths_for_job(job_id: str) -> List[str]:
    """Return file_url for all UPLOADED files belonging to a job."""
    entities = _files().query_entities(
        f"PartitionKey eq '{job_id}' and status eq 'UPLOADED'"
    )
    return [e["file_url"] for e in entities]


# ============================================================================
# OUTPUT LIFECYCLE MANAGEMENT
# ============================================================================


def _cleanup_expired_output_dirs(max_age_hours: int = 24) -> None:
    """Delete session output directories that are older than *max_age_hours*.

    Called on startup and lazily on result-fetch requests so the output
    volume does not grow unboundedly on Azure Container Apps (which has no
    built-in cron).
    """
    if not OUTPUT_DIR.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    for job_dir in OUTPUT_DIR.iterdir():
        if not job_dir.is_dir():
            continue
        try:
            if job_dir.stat().st_mtime < cutoff:
                shutil.rmtree(job_dir)
                logger.info(f"[TTL_CLEANUP] Deleted expired output dir: {job_dir.name}")
        except Exception as exc:
            logger.warning(f"[TTL_CLEANUP] Could not delete {job_dir}: {exc}")


def _cleanup_expired_upload_dirs(max_age_hours: int = 48) -> None:
    """Delete upload directories that are older than *max_age_hours*.

    Called on startup to prevent storage bloat from uploaded PDFs that are
    never explicitly deleted. Uploads are kept longer than outputs (48h vs 24h)
    to allow users to return and re-run analysis if needed.
    
    Args:
        max_age_hours: Delete uploads older than this many hours (default: 48)
    """
    if not UPLOAD_DIR.exists():
        return
    cutoff = time.time() - (max_age_hours * 3600)
    deleted_count = 0
    
    for job_dir in UPLOAD_DIR.iterdir():
        # Skip non-directories and the signed_url_cache
        if not job_dir.is_dir() or job_dir.name == "signed_url_cache":
            continue
        try:
            # Check modification time
            if job_dir.stat().st_mtime < cutoff:
                # Also delete associated Azure Table records
                job_id = job_dir.name
                try:
                    # Delete file records
                    file_entities = list(_files().query_entities(f"PartitionKey eq '{job_id}'"))
                    for entity in file_entities:
                        _files().delete_entity(
                            partition_key=entity["PartitionKey"],
                            row_key=entity["RowKey"],
                        )
                    # Delete job record
                    _jobs().delete_entity(partition_key="job", row_key=job_id)
                except Exception as e:
                    logger.warning(f"[TTL_CLEANUP] Could not delete table records for {job_id}: {e}")
                
                # Delete the upload directory
                shutil.rmtree(job_dir)
                deleted_count += 1
                logger.info(f"[TTL_CLEANUP] Deleted expired upload dir: {job_dir.name}")
        except Exception as exc:
            logger.warning(f"[TTL_CLEANUP] Could not delete upload dir {job_dir}: {exc}")
    
    if deleted_count > 0:
        logger.info(f"[TTL_CLEANUP] Cleaned up {deleted_count} expired upload directories")


def _cleanup_job_input_files(job_id: str) -> None:
    """Delete upload and data directories immediately after job completion/failure.

    Called after job finishes (success or failure) to free storage immediately.
    Only output files are kept with 24h TTL so users can download results.
    
    Args:
        job_id: The job ID whose input files should be deleted
    """
    # Security: Validate job_id is a proper UUID to prevent path traversal
    try:
        _validate_uuid(job_id, "job_id")
    except ValueError as e:
        logger.warning(f"[JOB_CLEANUP] Invalid job_id, skipping cleanup: {e}")
        return
    
    # Delete uploads directory (PDFs and input files)
    upload_dir = UPLOAD_DIR / job_id
    _validate_path_within_base(upload_dir, UPLOAD_DIR, "upload directory")
    if upload_dir.exists() and upload_dir.is_dir():
        try:
            shutil.rmtree(upload_dir)
            logger.info(f"[JOB_CLEANUP] Deleted uploads for job {job_id}")
        except Exception as e:
            logger.warning(f"[JOB_CLEANUP] Could not delete uploads for {job_id}: {e}")
    
    # Delete data directory (intermediate CSV files)
    data_dir = DATA_DIR / job_id
    _validate_path_within_base(data_dir, DATA_DIR, "data directory")
    if data_dir.exists() and data_dir.is_dir():
        try:
            shutil.rmtree(data_dir)
            logger.info(f"[JOB_CLEANUP] Deleted data files for job {job_id}")
        except Exception as e:
            logger.warning(f"[JOB_CLEANUP] Could not delete data files for {job_id}: {e}")
    
    # Note: Output directory is NOT deleted - kept for 24h TTL so users can download results


# ============================================================================
# BACKGROUND ORCHESTRATOR TRIGGER
# ============================================================================


def _get_max_pages_for_vendor(vendor: str) -> int:
    """
    Map vendor/carrier to max pages per PDF.
    
    Returns the hardcoded max_pages value based on vendor.
    """
    vendor_lower = vendor.lower().strip()
    
    # Vendor-specific page limits
    VENDOR_PAGE_LIMITS = {
        "att": 1000,
        "verizon": 3000,
        "telekom": 40000,
        "datanet": 100,
        "servicenow": 100,
        "vodafone": 100,
        "vivo": 100,
        "faktura": 100,
    }
    
    # Return mapped value or default to 100
    return VENDOR_PAGE_LIMITS.get(vendor_lower, 100)


async def _trigger_orchestrator_background(
    job_id: str,
    file_paths: List[str],
    orchestrator_message: str
) -> None:
    """
    Trigger the A2A orchestrator in the background (fire-and-forget).
    
    This runs asynchronously without blocking the upload/complete response.
    Frontend will poll /jobs/{job_id} for progress updates.
    
    Checks for job cancellation at key points to abort early if user cancels.
    """
    try:
        # Check if job was cancelled before starting
        job = _get_job(job_id)
        if job and job.get("status") == "CANCELLED":
            logger.info(f"[ORCHESTRATOR_CANCELLED] Job {job_id} was cancelled before orchestrator started")
            _cleanup_job_input_files(job_id)
            return
        
        # Extract vendor from orchestrator_message to determine max_pages
        vendor = ""
        if "Vendor/Carrier:" in orchestrator_message:
            # Extract vendor value from message
            vendor_line = [line for line in orchestrator_message.split("\n") if "Vendor/Carrier:" in line]
            if vendor_line:
                vendor = vendor_line[0].split("Vendor/Carrier:")[1].strip()
        
        # Get max_pages based on vendor
        max_pages = _get_max_pages_for_vendor(vendor)
        
        logger.info(f"[DEBUG_MAX_PAGES] job={job_id} vendor={vendor} max_pages={max_pages}")
        
        # Inject max_pages instruction into the message using regex to handle newlines
        modified_message = orchestrator_message
        if "Call invoice_pdf_to_tables" in modified_message:
            # Use regex to replace the instruction, handling optional "Important:" prefix and trailing whitespace/newlines
            import re
            # Pattern matches "Call invoice_pdf_to_tables...above" with or without existing max_pages parameter
            # This handles both fresh messages and messages that already have a max_pages value
            pattern = r'(Important:\s+)?Call invoice_pdf_to_tables for each PDF path listed above(\s+and pass max_pages=\d+)?\.?'
            replacement = r'\1Call invoice_pdf_to_tables for each PDF path listed above and pass max_pages=' + str(max_pages) + '.'
            modified_message = re.sub(pattern, replacement, modified_message)
            logger.info(f"[DEBUG_MODIFIED] job={job_id} replacement_made={modified_message != orchestrator_message}")
        
        logger.info(f"[ORCHESTRATOR] job={job_id} vendor={vendor}")
        
        parts = [
            {
                "kind": "text",
                "text": modified_message or "Process the uploaded file",
            }
        ]
        for fp in file_paths:
            parts.append(
                {
                    "kind": "file",
                    "file": {
                        "uri": fp,
                        "name": os.path.basename(fp),
                        "mimeType": (
                            "application/pdf"
                            if fp.endswith(".pdf")
                            else "application/octet-stream"
                        ),
                    },
                }
            )

        payload = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "contextId": job_id,
                "message": {
                    "role": "user",
                    "parts": parts,
                    "messageId": f"msg-{job_id}",
                    "kind": "message",
                },
            },
            "id": 1,
        }

        logger.info(
            "[ORCHESTRATOR_BACKGROUND] Starting job=%s files=%d method=message/send",
            job_id,
            len(file_paths),
        )

        # Use a very long timeout since this is background - we don't care if it takes hours
        async with httpx.AsyncClient(timeout=3600.0) as client:
            resp = await client.post(
                "http://localhost:8000",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            
            # Check if job was cancelled while orchestrator was running
            job = _get_job(job_id)
            if job and job.get("status") == "CANCELLED":
                logger.info(f"[ORCHESTRATOR_CANCELLED] Job {job_id} was cancelled during processing, aborting result handling")
                _cleanup_job_input_files(job_id)
                return
            
            if resp.status_code == 200:
                result = resp.json()
                logger.info(
                    f"[ORCHESTRATOR_BACKGROUND_OK] job={job_id} response={result}"
                )
                
                # Parse results and mark job as COMPLETED
                import json
                results_data = {}
                try:
                    # Extract artifacts from the orchestrator response
                    if "result" in result and "artifacts" in result["result"]:
                        artifacts = result["result"]["artifacts"]
                        # Get session ID from context
                        session_id = result.get("result", {}).get("contextId", job_id)
                        
                        # Security: Validate session_id is a proper UUID to prevent path traversal
                        try:
                            _validate_uuid(session_id, "session_id")
                        except ValueError as e:
                            logger.error(f"[ORCHESTRATOR_SECURITY] Invalid session_id from orchestrator: {e}")
                            # Fall back to job_id if session_id is invalid
                            session_id = job_id
                        
                        # Track which phases have completed
                        phase_1_complete = False
                        phase_2_complete = False
                        phase_3_complete = False
                        
                        # Process artifacts in order and update job status with delays
                        # so frontend polling can detect each phase transition
                        for artifact in artifacts:
                            artifact_name = artifact.get("name", "")
                            
                            # Check if job was cancelled between phases
                            job = _get_job(job_id)
                            if job and job.get("status") == "CANCELLED":
                                logger.info(f"[ORCHESTRATOR_CANCELLED] Job {job_id} cancelled during phase processing, aborting")
                                _cleanup_job_input_files(job_id)
                                return
                            
                            # Check for Phase 1 completion (PDF extraction)
                            if artifact_name == "phase_1_data_extraction_phase" and not phase_1_complete:
                                logger.info(f"[PHASE_1_COMPLETE] job={job_id} PDF extraction phase completed")
                                update_job(
                                    job_id,
                                    status="PROCESSING",
                                    current_phase="PHASE_1_COMPLETE",
                                    phase_message="PDF extraction completed",
                                )
                                phase_1_complete = True
                            
                            # Check for Phase 2 completion (Employee data loading)
                            elif artifact_name == "phase_2_employee_data_loading_phase" and not phase_2_complete:
                                logger.info(f"[PHASE_2_COMPLETE] job={job_id} Employee data loading phase completed")
                                update_job(
                                    job_id,
                                    status="PROCESSING",
                                    current_phase="PHASE_2_COMPLETE",
                                    phase_message="Employee data loaded from Databricks",
                                )
                                phase_2_complete = True
                            
                            # Parse Phase 3 results (Report generation)
                            elif artifact_name == "phase_3_report_generation_phase" and not phase_3_complete:
                                # Extract the JSON from the Phase 3 text
                                parts = artifact.get("parts", [])
                                for part in parts:
                                    if part.get("kind") == "text":
                                        text = part.get("text", "")
                                        # Find JSON block in the text
                                        if "```json" in text:
                                            json_start = text.find("```json") + 7
                                            json_end = text.find("```", json_start)
                                            if json_end > json_start:
                                                json_str = text[json_start:json_end].strip()
                                                raw_results = json.loads(json_str)
                                                
                                                # Log what we received for debugging
                                                logger.info(f"[PARSE_RESULTS] Received categories: {list(raw_results.get('categories', {}).keys())}")
                                                logger.info(f"[PARSE_RESULTS] Has csv_row_counts: {'csv_row_counts' in raw_results}")
                                                if "csv_row_counts" in raw_results:
                                                    logger.info(f"[PARSE_RESULTS] CSV row counts: {raw_results['csv_row_counts']}")
                                                
                                                # Get CSV row counts (actual exported rows)
                                                csv_counts = raw_results.get("csv_row_counts", {})
                                                
                                                # If LLM didn't include csv_row_counts, read from disk
                                                if not csv_counts:
                                                    logger.info(f"[PARSE_RESULTS] csv_row_counts missing, reading from disk for session {session_id}")
                                                    output_dir = OUTPUT_DIR / session_id
                                                    # Security: Validate path is within OUTPUT_DIR
                                                    _validate_path_within_base(output_dir, OUTPUT_DIR, "output directory")
                                                    csv_files = {
                                                        "zero_usage": output_dir / "1_ZERO_USAGE_USERS.csv",
                                                        "invoice_only": output_dir / "2_USER_NOT_FOUND.csv",
                                                        "fraud": output_dir / "3_INACTIVE_USERS.csv",
                                                        "employee_only": output_dir / "4_EMPLOYEE_ONLY_USERS.csv",
                                                    }
                                                    csv_counts = {}
                                                    for key, filepath in csv_files.items():
                                                        if filepath.exists():
                                                            # Count lines (subtract 1 for header)
                                                            with open(filepath, 'r', encoding='utf-8') as f:
                                                                line_count = sum(1 for line in f) - 1
                                                            csv_counts[key] = max(0, line_count)
                                                            logger.info(f"[PARSE_RESULTS] {key} CSV has {csv_counts[key]} rows")
                                                        else:
                                                            csv_counts[key] = 0
                                                            logger.info(f"[PARSE_RESULTS] {key} CSV not found")
                                                
                                                # Fix category names (LLM might return fraud_cases instead of fraud)
                                                categories = raw_results.get("categories", {})
                                                if "fraud_cases" in categories and "fraud" not in categories:
                                                    categories["fraud"] = categories.pop("fraud_cases")
                                                
                                                # Ensure all 4 required categories exist
                                                for key in ["zero_usage", "invoice_only", "fraud", "employee_only"]:
                                                    if key not in categories:
                                                        categories[key] = {"count": 0, "cost": 0.0}
                                                
                                                # Try to parse CSV export counts from text if missing from JSON
                                                # LLM often mentions "- Category: X rows" in the CSV export section
                                                if categories["zero_usage"]["count"] == 0:
                                                    match = re.search(r'Zero Usage:?\s+(\d+)\s+rows', text, re.IGNORECASE)
                                                    if match:
                                                        categories["zero_usage"]["count"] = int(match.group(1))
                                                        logger.info(f"[PARSE_RESULTS] Extracted zero_usage count from text: {match.group(1)}")
                                                
                                                if categories["invoice_only"]["count"] == 0:
                                                    match = re.search(r'Invoice Only:?\s+(\d+)\s+rows', text, re.IGNORECASE)
                                                    if match:
                                                        categories["invoice_only"]["count"] = int(match.group(1))
                                                        logger.info(f"[PARSE_RESULTS] Extracted invoice_only count from text: {match.group(1)}")
                                                
                                                if categories["fraud"]["count"] == 0:
                                                    match = re.search(r'Fraud Cases:?\s+(\d+)\s+rows', text, re.IGNORECASE)
                                                    if match:
                                                        categories["fraud"]["count"] = int(match.group(1))
                                                        logger.info(f"[PARSE_RESULTS] Extracted fraud count from text: {match.group(1)}")
                                                
                                                if categories["employee_only"]["count"] == 0:
                                                    match = re.search(r'Employee Only:?\s+(\d+)\s+rows', text, re.IGNORECASE)
                                                    if match:
                                                        categories["employee_only"]["count"] = int(match.group(1))
                                                        logger.info(f"[PARSE_RESULTS] Extracted employee_only count from text: {match.group(1)}")
                                                
                                                # Update category counts with actual CSV row counts (if available)
                                                # CSV counts are the actual exported rows and should take precedence
                                                for key in ["zero_usage", "invoice_only", "fraud", "employee_only"]:
                                                    if key in csv_counts:
                                                        categories[key]["count"] = csv_counts[key]
                                                
                                                # Build download_urls for all categories (frontend will disable based on count)
                                                download_urls = {
                                                    "zero_usage": f"/download/output/{session_id}/1_ZERO_USAGE_USERS.csv",
                                                    "invoice_only": f"/download/output/{session_id}/2_USER_NOT_FOUND.csv",
                                                    "fraud": f"/download/output/{session_id}/3_INACTIVE_USERS.csv",
                                                    "employee_only": f"/download/output/{session_id}/4_EMPLOYEE_ONLY_USERS.csv",
                                                }
                                                
                                                # Transform to frontend-expected structure
                                                results_data = {
                                                    "success": True,
                                                    "pdf_count": raw_results.get("pdf_count", 3),
                                                    "records_extracted": raw_results.get("records_extracted", 0),
                                                    "employee_count": raw_results.get("employee_count", 0),
                                                    "processing_time": raw_results.get("processing_time", 0),
                                                    "savings_summary": {
                                                        "summary": {
                                                            "total_issues": raw_results.get("total_issues", 0),
                                                            "total_cost": raw_results.get("total_cost", 0),
                                                            "monthly_savings": raw_results.get("monthly_savings", 0),
                                                            "annual_savings": raw_results.get("annual_savings", 0),
                                                        },
                                                        "months_analyzed": raw_results.get("months_analyzed", 3),
                                                        "categories": categories,
                                                    },
                                                    "download_urls": download_urls,
                                                }
                                                
                                                # Add Excel download URL
                                                if "excel_file" in raw_results:
                                                    excel_filename = raw_results["excel_file"]
                                                    results_data["excel_download_url"] = f"/download/output/{session_id}/{excel_filename}"
                                                
                                                # Mark Phase 3 as complete
                                                logger.info(f"[PHASE_3_COMPLETE] job={job_id} Report generation phase completed")
                                                phase_3_complete = True
                                                break
                    
                    # Final check before marking as completed
                    job = _get_job(job_id)
                    if job and job.get("status") == "CANCELLED":
                        logger.info(f"[ORCHESTRATOR_CANCELLED] Job {job_id} cancelled before final completion, aborting")
                        _cleanup_job_input_files(job_id)
                        return
                    
                    # Update job to COMPLETED with results
                    update_job(
                        job_id,
                        status="COMPLETED",
                        current_phase="COMPLETED",
                        phase_message="All phases completed successfully",
                        results=json.dumps(results_data) if results_data else "",
                    )
                    logger.info(f"[JOB_COMPLETED] job={job_id} issues={results_data.get('total_issues', 0)}")
                    
                    # Clean up input files immediately (uploads + data directories)
                    _cleanup_job_input_files(job_id)
                    
                except Exception as parse_error:
                    logger.warning(
                        f"[ORCHESTRATOR_PARSE_WARNING] job={job_id} Could not parse results: {parse_error}. Marking as completed anyway."
                    )
                    # Still mark as completed even if we can't parse results
                    update_job(
                        job_id,
                        status="COMPLETED",
                        current_phase="COMPLETED",
                        phase_message="Processing completed",
                        results="",
                    )
                    
                    # Clean up input files immediately even if parsing failed
                    _cleanup_job_input_files(job_id)
                    
            else:
                logger.error(
                    "[ORCHESTRATOR_BACKGROUND_ERROR] job=%s status=%d body=%s",
                    job_id,
                    resp.status_code,
                    resp.text[:500] if resp.text else "empty",
                )
                # Mark job as failed if orchestrator rejects it
                update_job(
                    job_id,
                    status="FAILED",
                    current_phase="ERROR",
                    error_message=f"Orchestrator returned {resp.status_code}",
                )
                
                # Clean up input files even on failure
                _cleanup_job_input_files(job_id)

    except Exception as e:
        logger.error(
            f"[ORCHESTRATOR_BACKGROUND_EXCEPTION] job={job_id} error={e}",
            exc_info=True,
        )
        # Mark job as failed
        update_job(
            job_id,
            status="FAILED",
            current_phase="ERROR",
            error_message=f"Orchestrator failed: {str(e)}",
        )
        
        # Clean up input files even on exception
        _cleanup_job_input_files(job_id)


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================


def create_upload_api() -> FastAPI:
    """Create FastAPI app for file uploads with 200 MB limit."""

    app = FastAPI(title="Mobile Contract Agent - File Upload API")

    @app.on_event("startup")
    async def startup_cleanup():
        """Delete old output and upload directories on container start."""
        _cleanup_expired_output_dirs()
        _cleanup_expired_upload_dirs()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def limit_upload_size(request: Request, call_next):
        """Middleware to enforce 200 MB upload limit."""
        if request.method == "POST" and "content-length" in request.headers:
            content_length = int(request.headers["content-length"])
            if content_length > MAX_UPLOAD_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={
                        "success": False,
                        "error": f"File too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.0f} MB",
                        "max_size_mb": MAX_UPLOAD_SIZE / (1024 * 1024),
                    },
                )
        return await call_next(request)

    # -----------------------------------------------------------------------
    # STEP 1 — Start a job session
    # -----------------------------------------------------------------------

    @app.post("/upload/job/start")
    async def start_upload_job(request: StartJobRequest):
        """
        STEP 1: Start a new upload job session.

        Creates a job ID (stored in SQLite) that must be passed to every
        subsequent upload call.  Survives container restarts — Azure SQL ready.
        """
        try:
            job = _create_job(request.user_id)
            return JSONResponse(job)
        except Exception as e:
            logger.error(f"[JOB_START_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # STEP 2 — Request a signed (token-protected) upload URL
    # -----------------------------------------------------------------------

    @app.post("/upload/url")
    async def request_signed_url(request: SignedUrlRequest):
        """
        STEP 2: Request a signed URL for a single file upload.

        Returns a token-protected PUT endpoint.  Each token is single-use and
        expires after `expires_in_seconds`.  File metadata is persisted in
        SQLite (Azure SQL ready).
        """
        try:
            job = _get_job(request.job_id)
            if not job:
                raise HTTPException(
                    status_code=404, detail=f"Job not found: {request.job_id}"
                )

            # Auto-detect file type from extension
            file_type = request.file_type
            if not file_type:
                ext = Path(request.filename).suffix.lower()
                if ext == ".pdf":
                    file_type = "pdf"
                elif ext == ".csv":
                    file_type = "csv"
                else:
                    file_type = "other"

            file_record = _add_file_to_job(
                request.job_id, request.filename, file_type, request.expires_in_seconds
            )

            # Token is embedded in the URL (Azure Blob SAS pattern)
            signed_url = (
                f"/upload/direct/{request.job_id}/{file_type}"
                f"/{Path(file_record['stored_relative']).name}"
                f"?token={file_record['upload_token']}"
            )

            logger.info(
                "[SIGNED_URL] job=%s file_id=%s type=%s file=%s",
                request.job_id,
                file_record["file_id"],
                file_type,
                request.filename,
            )

            return JSONResponse(
                {
                    "job_id": request.job_id,
                    "file_id": file_record["file_id"],
                    "upload_url": signed_url,
                    "file_url": file_record["file_url"],
                    "stored_relative": file_record["stored_relative"],
                    "expires_at": file_record["expires_at"],
                    "method": "PUT",
                    "headers": {
                        "Content-Type": request.content_type
                        or "application/octet-stream"
                    },
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[SIGNED_URL_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # STEP 3 — Receive the actual file bytes
    # -----------------------------------------------------------------------

    @app.put("/upload/direct/{job_id}/{file_type}/{filename}")
    async def direct_upload(
        job_id: str, file_type: str, filename: str, request: Request, token: str = None
    ):
        """
        STEP 3: Direct file upload endpoint.

        Validates the token issued in STEP 2, writes the file to disk
        (Azure Blob migration: replace write_bytes with blob_client.upload_blob),
        and marks the file UPLOADED in SQLite.
        """
        try:
            if not token:
                raise HTTPException(status_code=401, detail="Upload token required")

            # Look up file record by token — query by job partition, match token in Python
            entities = list(_files().query_entities(f"PartitionKey eq '{job_id}'"))
            row = next((dict(e) for e in entities if e.get("upload_token") == token), None)

            if not row:
                raise HTTPException(
                    status_code=404, detail="File record not found or token invalid"
                )

            file_id = row.get("file_id") or row["RowKey"]
            file_url = row["file_url"]
            exp = row["expires_at"].rstrip("Z")

            if datetime.fromisoformat(exp) < datetime.utcnow():
                raise HTTPException(status_code=401, detail="Upload token expired")

            # Read & size-check the body
            contents = await request.body()
            if len(contents) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.0f} MB",
                )

            # Save to disk — Azure Blob migration: replace with blob_client.upload_blob(contents)
            file_path = Path(file_url)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(contents)

            file_size_mb = len(contents) / (1024 * 1024)
            _update_file_status(file_id, job_id, "UPLOADED", size_bytes=len(contents))

            logger.info(
                "[DIRECT_UPLOAD] job=%s file_id=%s type=%s size=%.2fMB",
                job_id,
                file_id,
                file_type,
                file_size_mb,
            )

            return JSONResponse(
                {
                    "success": True,
                    "job_id": job_id,
                    "file_id": file_id,
                    "stored_at": str(file_path),
                    "size_bytes": len(contents),
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DIRECT_UPLOAD_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # STEP 4 — Notify completion & optionally trigger orchestrator
    # -----------------------------------------------------------------------

    @app.post("/upload/complete")
    async def upload_complete(request: UploadCompleteRequest):
        """
        STEP 4: Notify backend that all uploads for a job are complete.

        Updates job status in Azure Table Storage.
        STEP 5: Optionally triggers the phased orchestrator in background (non-blocking).
        
        Frontend polls /jobs/{job_id} for progress updates instead of waiting here.
        """
        try:
            job = _get_job(request.job_id)
            if not job:
                raise HTTPException(
                    status_code=404, detail=f"Job not found: {request.job_id}"
                )

            if request.success:
                update_job(request.job_id, status="PROCESSING", current_phase="PHASE_1_STARTING", phase_message="Starting PDF extraction...")
            else:
                update_job(request.job_id, status="FAILED", current_phase="ERROR")
                # Clean up input files if upload marked as failed
                _cleanup_job_input_files(request.job_id)

            orchestrator_triggered = False

            if request.trigger_orchestrator and request.success:
                file_paths = _get_all_file_paths_for_job(request.job_id)

                if file_paths:
                    # Trigger orchestrator in background (fire-and-forget)
                    asyncio.create_task(
                        _trigger_orchestrator_background(
                            request.job_id,
                            file_paths,
                            request.orchestrator_message or "Process the uploaded files"
                        )
                    )
                    orchestrator_triggered = True
                    logger.info(
                        "[UPLOAD_COMPLETE] job=%s orchestrator=triggered_in_background files=%d",
                        request.job_id,
                        len(file_paths),
                    )
                else:
                    logger.warning(
                        "[UPLOAD_COMPLETE] job=%s no files found, skipping orchestrator",
                        request.job_id,
                    )

            job_with_files = _get_job_with_files(request.job_id)

            return JSONResponse(
                {
                    "job": job_with_files,
                    "orchestrator_triggered": orchestrator_triggered,
                    "message": "Job submitted. Poll /jobs/{job_id} for progress." if orchestrator_triggered else "Upload complete.",
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[UPLOAD_COMPLETE_ERROR] {e}")
            # Note: job_id not available in this outer exception handler
            # Inner try-except already handles cleanup when job_id is available
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # JOB STATUS
    # -----------------------------------------------------------------------

    @app.get("/jobs/{job_id}")
    async def get_job_status(job_id: str):
        """Get current status of an upload job with progress details for polling."""
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            _validate_uuid(job_id, "job_id")
            
            job = _get_job_with_files(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
            
            # Parse results if completed
            results = None
            if job.get("status") == "COMPLETED" and job.get("results"):
                try:
                    results = json.loads(job["results"])
                except Exception as parse_err:
                    logger.warning(f"[JOB_STATUS] Could not parse results JSON: {parse_err}")
                    results = None
            
            # Return enhanced status for polling
            return JSONResponse({
                "job_id": job_id,
                "status": job.get("status", "UNKNOWN"),
                "current_phase": job.get("current_phase", ""),
                "phase_message": job.get("phase_message", ""),
                "error_message": job.get("error_message", ""),
                "created_at": job.get("created_at"),
                "updated_at": job.get("updated_at"),
                "results": results,
                "files": job.get("files", []),
            })
        except ValueError as e:
            # Security validation error
            logger.warning(f"[JOB_STATUS_SECURITY] job_id={job_id}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[GET_JOB_STATUS_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # LEGACY SIMPLE UPLOAD (kept for backward compatibility)
    # -----------------------------------------------------------------------

    @app.post("/upload")
    async def upload_file(file: UploadFile = File(...)):
        """
        Simple multipart upload — kept for backward compatibility.
        Prefer the signed-URL flow for large files.
        """
        try:
            file_id = str(uuid.uuid4())
            original_name = file.filename or "unknown"
            extension = Path(original_name).suffix
            saved_filename = f"{file_id}{extension}"
            file_path = UPLOAD_DIR / saved_filename

            logger.info(f"[UPLOAD] {original_name} -> {saved_filename}")
            contents = await file.read()

            if len(contents) > MAX_UPLOAD_SIZE:
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_UPLOAD_SIZE / (1024*1024):.0f} MB",
                )

            file_path.write_bytes(contents)
            file_size_mb = len(contents) / (1024 * 1024)
            logger.info(f"[OK] Saved {file_path} ({file_size_mb:.2f} MB)")

            return JSONResponse(
                {
                    "success": True,
                    "file_path": str(file_path),
                    "original_name": original_name,
                    "size_bytes": len(contents),
                    "size_mb": round(file_size_mb, 2),
                }
            )

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[UPLOAD_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # HEALTH
    # -----------------------------------------------------------------------

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "file-upload-api"}

    # -----------------------------------------------------------------------
    # DOWNLOAD / LIST — data directory
    # -----------------------------------------------------------------------

    @app.get("/download/data/{filename}")
    async def download_data_file(filename: str):
        """Download a CSV or other file from the data directory."""
        try:
            # Security: Sanitize filename to prevent path traversal
            safe_filename = _sanitize_filename(filename)
            file_path = DATA_DIR / safe_filename
            
            # Security: Validate path is within DATA_DIR
            _validate_path_within_base(file_path, DATA_DIR, "data file")
            if not file_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"File not found: {filename}"
                )
            if not file_path.is_file():
                raise HTTPException(
                    status_code=400, detail=f"Not a valid file: {safe_filename}"
                )
            # Path validation already done above
            media_type = (
                "text/csv" if filename.endswith(".csv") else "application/octet-stream"
            )
            return FileResponse(
                path=file_path, media_type=media_type, filename=safe_filename
            )
        except ValueError as e:
            # Security validation error
            logger.warning(f"[DOWNLOAD_DATA_SECURITY] {filename}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DOWNLOAD_DATA_ERROR] {filename}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/list/data")
    async def list_data_files():
        """List all files in the data directory."""
        try:
            files = []
            for fp in DATA_DIR.glob("*"):
                if fp.is_file():
                    stat = fp.stat()
                    files.append(
                        {
                            "filename": fp.name,
                            "size_bytes": stat.st_size,
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "modified": stat.st_mtime,
                            "download_url": f"/download/data/{fp.name}",
                        }
                    )
            return {"files": files, "count": len(files)}
        except Exception as e:
            logger.error(f"[LIST_DATA_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # ANALYSIS RESULTS
    # -----------------------------------------------------------------------

    @app.get("/analysis/results/{job_id}")
    async def get_analysis_results(job_id: str):
        """
        Get analysis results for a completed job.

        Returns the savings summary JSON and download URLs for all generated
        CSV / Excel reports.  Job is looked up from SQLite (Azure SQL ready).
        """
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            _validate_uuid(job_id, "job_id")
            
            job = _get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

            # Lazily purge old directories from previous runs (24h outputs, 48h uploads)
            _cleanup_expired_output_dirs()
            _cleanup_expired_upload_dirs()

            job_output_dir = OUTPUT_DIR / job_id
            # Security: Validate path is within OUTPUT_DIR
            _validate_path_within_base(job_output_dir, OUTPUT_DIR, "output directory")
            
            savings_summary_path = job_output_dir / "savings_summary.json"
            if not savings_summary_path.exists():
                logger.warning(
                    f"[ANALYSIS_RESULTS] No savings summary found for job {job_id}"
                )
                return {
                    "job_id": job_id,
                    "status": job["status"],
                    "savings_summary": None,
                    "files": [],
                    "download_urls": {},
                }

            with open(savings_summary_path, "r") as f:
                savings_summary = json.load(f)

            download_urls: Dict[str, str] = {}
            csv_mapping = {
                "zero_usage": "1_ZERO_USAGE_USERS.csv",
                "invoice_only": "2_USER_NOT_FOUND.csv",
                "fraud": "3_INACTIVE_USERS.csv",
                "employee_only": "4_EMPLOYEE_ONLY_USERS.csv",
            }
            for key, fname in csv_mapping.items():
                if (job_output_dir / fname).exists():
                    download_urls[key] = f"/download/output/{job_id}/{fname}"

            if savings_summary.get("excel_filename"):
                excel_path = job_output_dir / savings_summary["excel_filename"]
                if excel_path.exists():
                    download_urls["excel"] = (
                        f"/download/output/{job_id}/{savings_summary['excel_filename']}"
                    )

            output_files = []
            if job_output_dir.exists():
                for fp in job_output_dir.glob("*"):
                    if fp.is_file() and fp.suffix in (".csv", ".xlsx", ".json"):
                        stat = fp.stat()
                        output_files.append(
                            {
                                "filename": fp.name,
                                "size_bytes": stat.st_size,
                                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                                "modified": stat.st_mtime,
                                "download_url": f"/download/output/{job_id}/{fp.name}",
                            }
                        )

            logger.info(f"[ANALYSIS_RESULTS] Returning results for job {job_id}")
            return {
                "job_id": job_id,
                "status": job["status"],
                "savings_summary": savings_summary,
                "files": output_files,
                "download_urls": download_urls,
            }

        except ValueError as e:
            # Security validation error
            logger.warning(f"[ANALYSIS_RESULTS_SECURITY] job_id={job_id}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[ANALYSIS_RESULTS_ERROR] {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # DOWNLOAD / LIST — output directory
    # -----------------------------------------------------------------------

    @app.get("/download/output/{job_id}/{filename}")
    async def download_output_file(job_id: str, filename: str):
        """Download an analysis result file (CSV, Excel, JSON) from a session output directory."""
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            _validate_uuid(job_id, "job_id")
            # Security: Sanitize filename to prevent path traversal
            safe_filename = _sanitize_filename(filename)
            
            job_output_dir = OUTPUT_DIR / job_id
            _validate_path_within_base(job_output_dir, OUTPUT_DIR, "output directory")
            
            file_path = job_output_dir / safe_filename
            _validate_path_within_base(file_path, OUTPUT_DIR, "output file")
            if not file_path.exists():
                raise HTTPException(
                    status_code=404, detail=f"File not found: {filename}"
                )
            if not file_path.is_file():
                raise HTTPException(
                    status_code=400, detail=f"Not a valid file: {safe_filename}"
                )
            # Path validation already done above

            media_type_map = {
                ".csv": "text/csv",
                ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".json": "application/json",
            }
            media_type = media_type_map.get(
                file_path.suffix, "application/octet-stream"
            )
            return FileResponse(
                path=file_path, media_type=media_type, filename=safe_filename
            )

        except ValueError as e:
            # Security validation error
            logger.warning(f"[DOWNLOAD_OUTPUT_SECURITY] job_id={job_id} filename={filename}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[DOWNLOAD_OUTPUT_ERROR] {filename}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/list/output")
    async def list_output_files():
        """List all files in the output directory."""
        try:
            files = []
            for fp in OUTPUT_DIR.glob("*"):
                if fp.is_file():
                    stat = fp.stat()
                    files.append(
                        {
                            "filename": fp.name,
                            "size_bytes": stat.st_size,
                            "size_mb": round(stat.st_size / (1024 * 1024), 2),
                            "modified": stat.st_mtime,
                            "download_url": f"/download/output/{fp.name}",
                        }
                    )
            return {"files": files, "count": len(files)}
        except Exception as e:
            logger.error(f"[LIST_OUTPUT_ERROR] {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # CLEANUP — delete a job's upload folder after pipeline completes
    # -----------------------------------------------------------------------

    @app.delete("/cleanup/{job_id}")
    async def cleanup_job_uploads(job_id: str):
        """
        Delete all uploaded files for a job session and purge its Azure Table records.

        Called by the UI after the pipeline has completed.  Removes the job's
        subdirectory under uploads/ so storage does not grow unboundedly, then
        deletes the job row from jobtracker and all file rows from filesmetadata.
        Each job's files are isolated in uploads/{job_id}/ so only that
        session's data is affected — safe for concurrent users.
        """
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            _validate_uuid(job_id, "job_id")
            
            # --- 1. Delete files from disk ---
            job_dir = UPLOAD_DIR / job_id
            _validate_path_within_base(job_dir, UPLOAD_DIR, "cleanup directory")
            
            if job_dir.exists() and job_dir.is_dir():
                shutil.rmtree(job_dir)
                logger.info(f"[CLEANUP] Deleted upload folder for job {job_id}")

            # --- 2. Delete file records from filesmetadata table ---
            deleted_files = 0
            try:
                file_entities = list(_files().query_entities(f"PartitionKey eq '{job_id}'"))
                for entity in file_entities:
                    _files().delete_entity(
                        partition_key=entity["PartitionKey"],
                        row_key=entity["RowKey"],
                    )
                    deleted_files += 1
                if deleted_files:
                    logger.info(f"[CLEANUP] Deleted {deleted_files} file record(s) from {FILE_TABLE_NAME} for job {job_id}")
            except Exception as e:
                logger.warning(f"[CLEANUP] Could not delete file records for job {job_id}: {e}")

            # --- 3. Delete job row from jobtracker table ---
            try:
                _jobs().delete_entity(partition_key="job", row_key=job_id)
                logger.info(f"[CLEANUP] Deleted job row from {JOB_TABLE_NAME} for job {job_id}")
            except Exception as e:
                logger.warning(f"[CLEANUP] Could not delete job row for {job_id}: {e}")

            return {
                "success": True,
                "message": f"Job {job_id} cleaned up (files deleted, {deleted_files} file record(s) removed from tables)",
            }
        except ValueError as e:
            # Security validation error
            logger.warning(f"[CLEANUP_SECURITY] job_id={job_id}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CLEANUP_ERROR] job_id={job_id}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # -----------------------------------------------------------------------
    # CANCEL — mark a job as cancelled AND clean up its upload folder
    # -----------------------------------------------------------------------

    @app.post("/cancel/{job_id}")
    async def cancel_job(job_id: str):
        """
        Cancel a running job and clean up its uploaded files.

        Called by the UI when the user reloads the page, closes the tab, or
        navigates away while a pipeline is still running.  Marks the job as
        cancelled so that long-running tools can check and bail out early,
        and immediately deletes the job's upload folder to free storage.
        Safe for concurrent users — only the specified job_id is affected.
        
        Idempotent: Multiple cancel calls for the same job are safe.
        """
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            try:
                _validate_uuid(job_id, "job_id")
            except ValueError as e:
                logger.warning(f"[CANCEL_SECURITY] Invalid job_id: {e}")
                raise HTTPException(status_code=403, detail="Access denied")
            
            # Check if job exists before trying to cancel
            job = _get_job(job_id)
            
            if job:
                # Mark job as cancelled in Azure Table Storage
                update_job(
                    job_id,
                    status="CANCELLED",
                    current_phase="CANCELLED",
                    phase_message="Job cancelled by user",
                )
                logger.info(f"[CANCEL] Job {job_id} marked as cancelled")
            else:
                # Job doesn't exist - might have been cleaned up already
                logger.info(f"[CANCEL] Job {job_id} not found (already cancelled or cleaned up)")

            # Clean up all input files for this job (uploads + data directories)
            # Use the same cleanup function used on job completion
            _cleanup_job_input_files(job_id)

            return {
                "success": True,
                "message": f"Job {job_id} cancelled and all input files cleaned up",
            }
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[CANCEL_ERROR] job_id={job_id}: {e}")
            # Return success anyway to avoid errors on multiple cancel attempts
            return {
                "success": True,
                "message": f"Cancel attempted for job {job_id}",
                "note": str(e)
            }

    # -----------------------------------------------------------------------
    # EMPLOYEE-ONLY FILTERED DOWNLOAD
    # -----------------------------------------------------------------------

    @app.get("/output/employee-only-filtered")
    async def download_employee_only_filtered(country: str, job_id: str):
        """
        Return a filtered version of 4_EMPLOYEE_ONLY_USERS.csv containing
        only rows where U_COUNTRY matches the requested country string.

        Used by the UI when the analyst wants country-specific output instead
        of the full global employee-only list.

        Args:
            country: Country name to filter by (e.g. "Germany", "United States of America").
            job_id:  Job / session ID whose output directory to read from.
        """
        try:
            # Security: Validate job_id is a proper UUID to prevent path traversal
            _validate_uuid(job_id, "job_id")
            
            job_output_dir = OUTPUT_DIR / job_id
            _validate_path_within_base(job_output_dir, OUTPUT_DIR, "output directory")
            
            employee_csv = job_output_dir / "4_EMPLOYEE_ONLY_USERS.csv"
            if not employee_csv.exists():
                raise HTTPException(
                    status_code=404,
                    detail="Employee Only CSV not found — run the pipeline first",
                )

            try:
                import pandas as pd
            except ImportError:
                raise HTTPException(
                    status_code=500, detail="pandas is not installed on the server"
                )

            df = pd.read_csv(employee_csv)

            if "U_COUNTRY" not in df.columns:
                raise HTTPException(
                    status_code=422,
                    detail="U_COUNTRY column not found in Employee Only CSV — cannot filter by country",
                )

            filtered = df[
                df["U_COUNTRY"].str.strip().str.lower() == country.strip().lower()
            ]
            logger.info(
                f"[EMPLOYEE_FILTER] country={country!r} total={len(df)} filtered={len(filtered)}"
            )

            csv_buffer = io.StringIO()
            filtered.to_csv(csv_buffer, index=False)
            csv_bytes = csv_buffer.getvalue().encode("utf-8")

            safe_country = country.replace(" ", "_").replace("/", "_")
            filename = f"4_EMPLOYEE_ONLY_{safe_country.upper()}.csv"
            return Response(
                content=csv_bytes,
                media_type="text/csv",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )

        except ValueError as e:
            # Security validation error
            logger.warning(f"[EMPLOYEE_FILTER_SECURITY] job_id={job_id}: {e}")
            raise HTTPException(status_code=403, detail="Access denied")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"[EMPLOYEE_FILTER_ERROR] country={country}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    return app


if __name__ == "__main__":
    import uvicorn

    app = create_upload_api()
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
