// Utility to upload a file to the agent's /upload endpoint
export async function uploadFileToAgent(file: File, agentBaseUrl: string): Promise<string> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`${agentBaseUrl}/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  // Adjust this based on your backend's response structure
  const data = await response.json();
  if (data && data.file_path) {
    return data.file_path;
  }
  throw new Error('No file path returned from upload');
}
