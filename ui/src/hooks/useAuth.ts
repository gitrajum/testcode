/**
 * Custom authentication hook that wraps MSAL functionality.
 *
 * Provides a simplified interface for authentication operations:
 * - Login/logout
 * - Token acquisition for API calls
 * - Authentication state checks
 * - Silent token refresh
 *
 * @example
 * ```tsx
 * const { login, logout, getAccessToken, isAuthenticated, user } = useAuth();
 *
 * // Login
 * await login();
 *
 * // Get token for API call
 * const token = await getAccessToken();
 *
 * // Logout
 * await logout();
 * ```
 */

import { useCallback, useEffect, useState } from 'react';
import { useMsal, useIsAuthenticated } from '@azure/msal-react';
import {
  InteractionRequiredAuthError,
  InteractionStatus,
  AccountInfo,
  AuthenticationResult,
} from '@azure/msal-browser';
import { loginRequest, tokenRequest, silentRequest } from '@/lib/auth/msalConfig';

export interface UseAuthReturn {
  /** Whether the user is authenticated */
  isAuthenticated: boolean;
  /** Whether authentication is in progress */
  isLoading: boolean;
  /** Current user account information */
  user: AccountInfo | null;
  /** Login with redirect */
  login: () => Promise<void>;
  /** Logout with redirect */
  logout: () => Promise<void>;
  /** Get access token for API calls (tries silent, falls back to interactive) */
  getAccessToken: () => Promise<string>;
  /** Try to sign in silently (restore session) */
  trySignInSilent: () => Promise<boolean>;
  /** Error state from authentication operations */
  error: Error | null;
}

/**
 * Custom hook for Azure AD authentication using MSAL.
 *
 * @returns Authentication state and methods
 */
export function useAuth(): UseAuthReturn {
  const { instance, accounts, inProgress } = useMsal();
  const isAuthenticated = useIsAuthenticated();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const account = accounts[0] || null;

  /**
   * Login with redirect flow.
   * User will be redirected to Azure AD login page.
   */
  const login = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Clear the logout flag when user explicitly logs in
      sessionStorage.removeItem('userLoggedOut');

      await instance.loginRedirect(loginRequest);
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Login failed');
      setError(error);
      console.error('[Auth] Login error:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [instance]);

  /**
   * Logout with redirect flow.
   * Clears local session and redirects to Azure AD logout.
   */
  const logout = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Set a flag to prevent automatic sign-in after logout
      sessionStorage.setItem('userLoggedOut', 'true');

      await instance.logoutRedirect({
        account: account,
      });
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Logout failed');
      setError(error);
      console.error('[Auth] Logout error:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  }, [instance, account]);

  /**
   * Acquire access token for API calls.
   *
   * Attempts silent token acquisition first (from cache or refresh token).
   * Falls back to interactive login if silent acquisition fails.
   *
   * @returns Access token string
   * @throws Error if token acquisition fails
   */
  const getAccessToken = useCallback(async (): Promise<string> => {
    if (!account) {
      throw new Error('No authenticated account. Please login first.');
    }

    setError(null);

    try {
      // Try silent token acquisition first
      const response: AuthenticationResult = await instance.acquireTokenSilent({
        ...silentRequest,
        account: account,
      });

      console.log('[Auth] Token acquired silently');
      return response.accessToken;
    } catch (err) {
      console.warn('[Auth] Silent token acquisition failed:', err);

      // If silent acquisition fails due to interaction required, redirect for interactive login
      if (err instanceof InteractionRequiredAuthError) {
        try {
          // acquireTokenRedirect returns void and redirects the user
          await instance.acquireTokenRedirect({
            ...tokenRequest,
            account: account,
          });

          // This code won't be reached as redirect happens
          throw new Error('Redirecting for authentication');
        } catch (interactiveErr) {
          const error = interactiveErr instanceof Error
            ? interactiveErr
            : new Error('Token acquisition failed');
          setError(error);
          console.error('[Auth] Interactive token acquisition failed:', error);
          throw error;
        }
      }

      // Other errors
      const error = err instanceof Error ? err : new Error('Token acquisition failed');
      setError(error);
      throw error;
    }
  }, [instance, account]);

  /**
   * Try to sign in silently (restore existing session).
   *
   * Attempts to restore user session without user interaction.
   * Useful for automatic login on app initialization.
   *
   * @returns true if silent sign-in succeeded, false otherwise
   */
  const trySignInSilent = useCallback(async (): Promise<boolean> => {
    // Check if user explicitly logged out
    const userLoggedOut = sessionStorage.getItem('userLoggedOut');
    if (userLoggedOut === 'true') {
      console.log('[Auth] Skipping silent sign-in - user explicitly logged out');
      return false;
    }

    // Don't try if already authenticated or interaction in progress
    if (isAuthenticated || inProgress !== InteractionStatus.None) {
      return isAuthenticated;
    }

    setError(null);

    try {
      console.log('[Auth] Attempting silent sign-in');
      const response = await instance.ssoSilent(loginRequest);
      console.log('[Auth] Silent sign-in successful');
      return true;
    } catch (err) {
      // Silent sign-in failure is expected if no session exists
      console.log('[Auth] Silent sign-in failed (expected if no existing session)');
      return false;
    }
  }, [instance, isAuthenticated, inProgress]);

  return {
    isAuthenticated,
    isLoading: isLoading || inProgress !== InteractionStatus.None,
    user: account,
    login,
    logout,
    getAccessToken,
    trySignInSilent,
    error,
  };
}
