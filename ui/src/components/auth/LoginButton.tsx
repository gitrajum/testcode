"use client";

import React from 'react';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { LogIn, Loader2 } from 'lucide-react';

export interface LoginButtonProps {
  /** Button variant */
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  /** Button size */
  size?: "default" | "sm" | "lg" | "icon";
  /** Custom class name */
  className?: string;
  /** Button text */
  children?: React.ReactNode;
}

/**
 * Login button component.
 *
 * Triggers Azure AD login flow when clicked.
 */
export function LoginButton({
  variant = "default",
  size = "default",
  className,
  children = "Sign in"
}: LoginButtonProps) {
  const { login, isLoading } = useAuth();

  const handleLogin = async () => {
    try {
      await login();
    } catch (err) {
      console.error('Login failed:', err);
    }
  };

  return (
    <Button
      onClick={handleLogin}
      disabled={isLoading}
      variant={variant}
      size={size}
      className={className}
    >
      {isLoading ? (
        <>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Signing in...
        </>
      ) : (
        <>
          <LogIn className="mr-2 h-4 w-4" />
          {children}
        </>
      )}
    </Button>
  );
}
