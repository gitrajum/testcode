export const ENV = {
  // API Configuration
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  NEXT_PUBLIC_WS_URL: process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000',
  NODE_ENV: process.env.NODE_ENV || 'development',

  // Azure AD Authentication Configuration
  AZURE_CLIENT_ID: process.env.NEXT_PUBLIC_AZURE_CLIENT_ID || '',
  AZURE_TENANT_ID: process.env.NEXT_PUBLIC_AZURE_TENANT_ID || '',
  AZURE_REDIRECT_URI: process.env.NEXT_PUBLIC_AZURE_REDIRECT_URI || (
    typeof window !== 'undefined' ? window.location.origin : 'http://localhost:3000'
  ),
  AZURE_API_SCOPE: process.env.NEXT_PUBLIC_AZURE_API_SCOPE || '',
};

/**
 * Validates that required Azure AD configuration is present.
 * Only validates in browser environment (not during build).
 * @throws Error if required configuration is missing
 */
export function validateAuthConfig(): void {
  // Skip validation during build time (server-side pre-rendering)
  if (typeof window === 'undefined') {
    return;
  }

  const missingVars: string[] = [];

  if (!ENV.AZURE_CLIENT_ID) missingVars.push('NEXT_PUBLIC_AZURE_CLIENT_ID');
  if (!ENV.AZURE_TENANT_ID) missingVars.push('NEXT_PUBLIC_AZURE_TENANT_ID');
  if (!ENV.AZURE_API_SCOPE) missingVars.push('NEXT_PUBLIC_AZURE_API_SCOPE');

  if (missingVars.length > 0) {
    throw new Error(
      `Missing required Azure AD configuration: ${missingVars.join(', ')}. ` +
      'Please check your .env.local file against .env.local.example'
    );
  }
}
