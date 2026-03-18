"use client";

import React from 'react';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { LogOut, Loader2 } from 'lucide-react';

export interface LogoutButtonProps {
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
 * Logout button component.
 *
 * Triggers Azure AD logout flow when clicked.
 */
export function LogoutButton({
  variant = "outline",
  size = "default",
  className,
  children = "Sign out"
}: LogoutButtonProps) {
  const { logout, isLoading } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
    } catch (err) {
      console.error('Logout failed:', err);
    }
  };

  return (
    <Button
      onClick={handleLogout}
      disabled={isLoading}
      variant={variant}
      size={size}
      className={className}
    >
      {isLoading ? (
        <>
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          Signing out...
        </>
      ) : (
        <>
          <LogOut className="mr-2 h-4 w-4" />
          {children}
        </>
      )}
    </Button>
  );
}
