import React, { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/layout/Header";
import { TabContent } from "@/components/layout/TabContent";
import { useAppState } from "@/hooks/useAppState";
import { useAuth } from "@/hooks/useAuth";
import { useHostState } from "@/a2a/state/host/hostStateContext";
import { useAppState as useAppContext } from "@/a2a/state/app/appStateContext";
import { A2AClient } from "@/a2a/client";
import { ENV } from "@/lib/env";
import { Loader2 } from "lucide-react";

export const App: React.FC = () => {
    const router = useRouter();
    const {
        activeTab,
        showAgentDetails,
        selectedAgent,
        conversation,
        handleTabChange,
        handleOpenConversation
    } = useAppState();

    const { isAuthenticated, isLoading: authLoading, getAccessToken, trySignInSilent } = useAuth();
    const { isLoaded: hostStateLoaded } = useHostState();
    const { isLoaded: appStateLoaded } = useAppContext();

    // Try silent sign-in on mount
    useEffect(() => {
        if (!isAuthenticated && !authLoading) {
            trySignInSilent();
        }
    }, [isAuthenticated, authLoading, trySignInSilent]);

    // Redirect to login if not authenticated after loading
    useEffect(() => {
        if (!authLoading && !isAuthenticated) {
            router.push('/login');
        }
    }, [isAuthenticated, authLoading, router]);

    // Configure A2A client with token provider
    useEffect(() => {
        if (isAuthenticated && typeof window !== 'undefined') {
            // Access the global A2A client instance and set the token provider
            // This is a simplified approach - you may want to use a context provider instead
            const client = new A2AClient(ENV.NEXT_PUBLIC_API_URL, fetch, getAccessToken);
            // Store client instance globally or in context for use by components
            (window as any).__a2aClient = client;
        }
    }, [isAuthenticated, getAccessToken]);

    // Show loading state while checking authentication or loading data
    if (authLoading || !hostStateLoaded || !appStateLoaded) {
        return (
            <div className="h-screen flex items-center justify-center">
                <div className="text-center">
                    <Loader2 className="h-12 w-12 animate-spin text-primary mx-auto mb-4" />
                    <div className="text-muted-foreground text-lg mb-2">
                        {authLoading ? 'Authenticating...' : 'Loading Mobile Invoice Analyser UI...'}
                    </div>
                    <div className="text-muted-foreground/60 text-sm">Please wait</div>
                </div>
            </div>
        );
    }

    // Don't render if not authenticated (will redirect)
    if (!isAuthenticated) {
        return null;
    }

    return (
        <div className="h-screen flex flex-col overflow-hidden max-h-screen">
            <Header
                activeTab={activeTab}
                onTabChange={handleTabChange}
            />

            <TabContent
                activeTab={activeTab}
                selectedAgent={selectedAgent}
                showAgentDetails={showAgentDetails}
                conversation={conversation}
                onChatTabChange={activeTab === "chat" ? () => {} : undefined}
                onOpenConversation={handleOpenConversation}
            />
        </div>
    );
};
