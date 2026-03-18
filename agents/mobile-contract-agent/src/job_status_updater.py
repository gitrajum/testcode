"""
Shared utility for updating job status in Azure Table Storage.

This module can be imported by both file_upload_api.py and invoice_processor.py
to update job status without circular dependencies.
"""
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def update_job_status(job_id: str, **fields) -> None:
    """
    Update job status in Azure Table Storage.
    
    Args:
        job_id: The job ID to update
        **fields: Fields to update (status, current_phase, phase_message, error_message, results, etc.)
    """
    try:
        from azure.data.tables import TableServiceClient
        from azure.identity import DefaultAzureCredential
        
        # Try connection string first (for local development/backwards compatibility)
        conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if conn_str:
            table_service = TableServiceClient.from_connection_string(conn_str, logging_enable=False)
        else:
            # Use managed identity with DefaultAzureCredential (production/secure)
            account = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
            if not account:
                logger.error(f"[JOB_UPDATE_ERROR] AZURE_STORAGE_ACCOUNT_NAME not set, cannot update job {job_id}")
                return
            credential = DefaultAzureCredential()
            table_service = TableServiceClient(
                endpoint=f"https://{account}.table.core.windows.net",
                credential=credential,
                logging_enable=False,
            )
        
        table_client = table_service.get_table_client("jobtracker")
        
        # Try to get the existing job entity, create minimal one if it doesn't exist
        # NOTE: jobtracker table schema uses PartitionKey="job" (fixed), RowKey=job_id
        try:
            entity = table_client.get_entity(partition_key="job", row_key=job_id)
        except Exception as e:
            logger.warning(f"[JOB_UPDATE] Job {job_id} not found in table, creating new entity for update")
            # Create a minimal entity - the upsert will create it if it doesn't exist
            entity = {
                "PartitionKey": "job",
                "RowKey": job_id,
                "job_id": job_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        
        # Update fields
        for key, value in fields.items():
            entity[key] = value
        
        # Always update timestamp
        entity["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        # Upsert the entity (will create if doesn't exist, update if it does)
        table_client.upsert_entity(entity)
        logger.info(f"[JOB_UPDATE] job={job_id} updates={list(fields.keys())}")
        
    except Exception as e:
        logger.error(f"[JOB_UPDATE_ERROR] Failed to update job {job_id}: {e}", exc_info=True)
