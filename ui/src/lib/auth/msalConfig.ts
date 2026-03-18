/**
 * Microsoft Authentication Library (MSAL) configuration for Azure AD authentication.
 *
 * This module configures the MSAL PublicClientApplication for browser-based
 * authentication with Azure AD using the Authorization Code Flow with PKCE.
 *
 * @see https://learn.microsoft.com/en-us/azure/active-directory/develop/tutorial-v2-react
 */

import { Configuration, PublicClientApplication, LogLevel } from '@azure/msal-browser';
import { ENV, validateAuthConfig } from '@/lib/env';

/**
 * MSAL configuration for Azure AD authentication.
 *
 * Uses Authorization Code Flow with PKCE (Proof Key for Code Exchange)
 * which is the recommended flow for single-page applications.
 */
export const msalConfig: Configuration = {
  auth: {
    clientId: ENV.AZURE_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${ENV.AZURE_TENANT_ID}`,
    redirectUri: ENV.AZURE_REDIRECT_URI,
    postLogoutRedirectUri: ENV.AZURE_REDIRECT_URI,
    navigateToLoginRequestUrl: true,
  },
  cache: {
    cacheLocation: 'sessionStorage', // Use sessionStorage for better security
    storeAuthStateInCookie: false,   // Set to true for IE11/Edge support
  },
  system: {
    loggerOptions: {
      loggerCallback: (level: LogLevel, message: string, containsPii: boolean) => {
        if (containsPii) return; // Don't log PII

        switch (level) {
          case LogLevel.Error:
            console.error('[MSAL]', message);
            break;
          case LogLevel.Info:
            console.info('[MSAL]', message);
            break;
          case LogLevel.Verbose:
            console.debug('[MSAL]', message);
            break;
          case LogLevel.Warning:
            console.warn('[MSAL]', message);
            break;
        }
      },
      logLevel: ENV.NODE_ENV === 'development' ? LogLevel.Verbose : LogLevel.Warning,
    },
    allowNativeBroker: false, // Disable native broker for web apps
  },
};

/**
 * Login request configuration.
 * Specifies the scopes to request during user sign-in.
 */
export const loginRequest = {
  scopes: ['User.Read'], // Basic profile info from Microsoft Graph
  prompt: 'select_account', // Always show account selection
};

/**
 * API access token request configuration.
 * Used when acquiring tokens to call the backend API.
 */
export const tokenRequest = {
  scopes: [ENV.AZURE_API_SCOPE],
  forceRefresh: false, // Use cached token if available
};

/**
 * Silent token request configuration.
 * Used for silent token acquisition (automatic refresh).
 */
export const silentRequest = {
  scopes: [ENV.AZURE_API_SCOPE],
  forceRefresh: false,
};

/**
 * Creates and initializes the MSAL PublicClientApplication instance.
 *
 * @throws Error if required Azure AD configuration is missing
 * @returns Initialized PublicClientApplication instance
 */
export function createMsalInstance(): PublicClientApplication {
  // Validate configuration before creating instance
  validateAuthConfig();

  const msalInstance = new PublicClientApplication(msalConfig);

  return msalInstance;
}

/**
 * Singleton MSAL instance.
 * Exported for use throughout the application.
 */
export const msalInstance = createMsalInstance();
