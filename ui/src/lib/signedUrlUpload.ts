/**
 * Signed URL Upload Utility
 *
 * Implements a three-step upload process:
 * 1. Request signed URL from backend
 * 2. Upload file directly to storage using signed URL
 * 3. Notify backend of completion
 */

export interface SignedUrlResponse {
  job_id: string;
  file_id: string;
  upload_url: string;
  file_url: string;
  stored_relative: string;
  expires_at: string;
  method: string;
  headers: Record<string, string>;
}

export interface UploadJobStatus {
  job_id: string;
  user_id?: string;
  file_url: string;
  original_name: string;
  stored_relative: string;
  status: string;
  current_phase: string;
  created_at: string;
  updated_at: string;
  error_message?: string;
  upload_token: string;
  expires_at: string;
}

export interface UploadCompleteResponse {
  job: UploadJobStatus;
  orchestrator_triggered: boolean;
  orchestrator_result?: any;
}

/**
 * Start a new upload job session
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param userId - Optional user ID for tracking
 * @returns Job with job_id
 */
export async function startUploadJob(
  agentBaseUrl: string,
  userId?: string
): Promise<{ job_id: string; user_id?: string; status: string; created_at: string }> {
  const response = await fetch(`${agentBaseUrl}/upload/job/start`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_id: userId,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(`Failed to start job: ${error.error || response.statusText}`);
  }

  return response.json();
}

/**
 * Request a signed URL for file upload under an existing job
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param jobId - Job ID from startUploadJob
 * @param filename - Original filename
 * @param fileType - File type: pdf, csv, or other (auto-detected if not provided)
 * @param userId - Optional user ID for tracking
 * @param contentType - Optional MIME type
 * @returns Signed URL response with upload details
 */
export async function requestSignedUrl(
  agentBaseUrl: string,
  jobId: string,
  filename: string,
  fileType?: string,
  userId?: string,
  contentType?: string
): Promise<SignedUrlResponse> {
  const response = await fetch(`${agentBaseUrl}/upload/url`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      job_id: jobId,
      filename,
      file_type: fileType,
      user_id: userId,
      content_type: contentType,
      expires_in_seconds: 900, // 15 minutes
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(`Failed to request signed URL: ${error.error || response.statusText}`);
  }

  return response.json();
}

/**
 * Upload file directly using signed URL
 *
 * @param signedUrl - Signed URL from requestSignedUrl
 * @param file - File to upload
 * @param headers - Additional headers from signed URL response
 * @param onProgress - Optional progress callback (0-100)
 * @returns Upload result with job_id, file_id and stored_at path
 */
export async function uploadToSignedUrl(
  agentBaseUrl: string,
  signedUrl: string,
  file: File,
  headers: Record<string, string>,
  onProgress?: (progress: number) => void
): Promise<{ success: boolean; job_id: string; file_id: string; stored_at: string; size_bytes: number }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();

    // Track progress
    if (onProgress) {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100;
          onProgress(percentComplete);
        }
      });
    }

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          const result = JSON.parse(xhr.responseText);
          resolve(result);
        } catch (e) {
          reject(new Error('Invalid JSON response from upload'));
        }
      } else {
        reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
      }
    });

    xhr.addEventListener('error', () => {
      reject(new Error('Network error during upload'));
    });

    xhr.addEventListener('abort', () => {
      reject(new Error('Upload aborted'));
    });

    const fullUrl = `${agentBaseUrl}${signedUrl}`;
    xhr.open('PUT', fullUrl, true);

    // Set headers
    for (const [key, value] of Object.entries(headers)) {
      xhr.setRequestHeader(key, value);
    }

    // Send file
    xhr.send(file);
  });
}

/**
 * Notify backend that upload is complete
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param jobId - Job ID from signed URL request
 * @param success - Whether upload succeeded
 * @param uploadedPath - Path returned from upload (optional)
 * @param triggerOrchestrator - Whether to automatically trigger orchestrator
 * @param orchestratorMessage - Custom message for orchestrator
 * @returns Upload complete response
 */
export async function notifyUploadComplete(
  agentBaseUrl: string,
  jobId: string,
  success: boolean,
  uploadedPath?: string,
  triggerOrchestrator: boolean = true,
  orchestratorMessage?: string
): Promise<UploadCompleteResponse> {
  const response = await fetch(`${agentBaseUrl}/upload/complete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      job_id: jobId,
      success,
      uploaded_path: uploadedPath,
      trigger_orchestrator: triggerOrchestrator,
      orchestrator_message: orchestratorMessage,
    }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(`Failed to notify upload complete: ${error.error || response.statusText}`);
  }

  return response.json();
}

/**
 * Get job status
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param jobId - Job ID to check
 * @returns Job status
 */
export async function getJobStatus(
  agentBaseUrl: string,
  jobId: string
): Promise<{ job: UploadJobStatus }> {
  const response = await fetch(`${agentBaseUrl}/jobs/${jobId}`);

  if (!response.ok) {
    const error = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(`Failed to get job status: ${error.error || response.statusText}`);
  }

  return response.json();
}

/**
 * Complete signed URL upload workflow for a single file
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param jobId - Job ID from startUploadJob
 * @param file - File to upload
 * @param onProgress - Optional progress callback (0-100)
 * @returns Upload result with file path
 */
export async function uploadFileWithSignedUrl(
  agentBaseUrl: string,
  jobId: string,
  file: File,
  onProgress?: (progress: number) => void
): Promise<{
  fileId: string;
  filePath: string;
  stored_at: string;
}> {
  try {
    // Step 1: Request signed URL
    if (onProgress) onProgress(0);
    const signedUrlResponse = await requestSignedUrl(
      agentBaseUrl,
      jobId,
      file.name,
      undefined, // Auto-detect file type
      undefined,
      file.type
    );

    // Step 2: Upload file to signed URL
    const uploadResult = await uploadToSignedUrl(
      agentBaseUrl,
      signedUrlResponse.upload_url,
      file,
      signedUrlResponse.headers,
      (progress) => {
        // Map 0-100 to 10-100 (reserve 0-10 for request)
        if (onProgress) onProgress(10 + progress * 0.9);
      }
    );

    if (onProgress) onProgress(100);

    return {
      fileId: signedUrlResponse.file_id,
      filePath: uploadResult.stored_at,
      stored_at: uploadResult.stored_at,
    };
  } catch (error) {
    throw error;
  }
}

/**
 * Upload multiple files with signed URLs under a single job
 *
 * @param agentBaseUrl - Base URL of the A2A agent server
 * @param files - Array of files to upload
 * @param userId - Optional user ID for tracking
 * @param onProgress - Optional progress callback per file (fileIndex, progress)
 * @param triggerOrchestrator - Whether to trigger orchestrator after all files uploaded
 * @param orchestratorMessage - Custom message for orchestrator
 * @returns Upload results with job ID and file paths
 */
export async function uploadMultipleFilesWithSignedUrl(
  agentBaseUrl: string,
  files: File[],
  userId?: string,
  onProgress?: (fileIndex: number, progress: number) => void,
  triggerOrchestrator: boolean = true,
  orchestratorMessage?: string
): Promise<{
  jobId: string;
  files: Array<{ fileId: string; filePath: string; filename: string }>;
  uploadResult?: UploadCompleteResponse;
}> {
  // Step 1: Start a new job
  const job = await startUploadJob(agentBaseUrl, userId);
  const jobId = job.job_id;

  // Step 2: Upload all files under this job
  const uploadedFiles = [];
  for (let i = 0; i < files.length; i++) {
    const file = files[i];
    const result = await uploadFileWithSignedUrl(
      agentBaseUrl,
      jobId,
      file,
      (progress) => {
        if (onProgress) onProgress(i, progress);
      }
    );
    uploadedFiles.push({
      fileId: result.fileId,
      filePath: result.filePath,
      filename: file.name,
    });
  }

  // Step 3: Notify backend that all uploads are complete
  const completeResult = await notifyUploadComplete(
    agentBaseUrl,
    jobId,
    true,
    undefined, // No single path since multiple files
    triggerOrchestrator,
    orchestratorMessage
  );

  return {
    jobId,
    files: uploadedFiles,
    uploadResult: completeResult,
  };
}
