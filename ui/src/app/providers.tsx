"use client"

import React, {ReactNode} from "react"
import {MsalProvider} from "@azure/msal-react";
import {msalInstance} from "@/lib/auth/msalConfig";
import {SettingsStateProvider} from "@/a2a/state/settings/settingsStateContext";
import {AgentStateProvider} from "@/a2a/state/agent/agentStateContext";
import {AppStateProvider} from "@/a2a/state/app/appStateContext";
import {HostStateProvider} from "@/a2a/state/host/hostStateContext";
import {ThemeProvider} from "@/contexts/ThemeContext";

export function Providers({children}: { children: ReactNode }) {
    return (
        <MsalProvider instance={msalInstance}>
            <ThemeProvider>
                <AppStateProvider>
                    <SettingsStateProvider>
                        <AgentStateProvider>
                            <HostStateProvider>
                                {children}
                            </HostStateProvider>
                        </AgentStateProvider>
                    </SettingsStateProvider>
                </AppStateProvider>
            </ThemeProvider>
        </MsalProvider>
    )
}
