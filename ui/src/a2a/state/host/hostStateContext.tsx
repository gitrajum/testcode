"use client";

import React, { createContext, useContext, useState, ReactNode, useEffect } from "react";
import {HostState} from "@/a2a/state/host/HostState";
import {AgentCard} from "@/a2a/schema";
import {ENV} from "@/lib/env";

// Constants for localStorage
const AGENTS_STORAGE_KEY = "a2a_agents";

// Utility functions for localStorage
const saveAgentsToStorage = (hostState: HostState) => {
    try {
        if (typeof window !== 'undefined') {
            localStorage.setItem(AGENTS_STORAGE_KEY, JSON.stringify(hostState.hosts));
        }
    } catch (error) {
        console.error("Failed to save agents to localStorage:", error);
    }
};

const createDefaultAgent = (): AgentCard => {
    const apiUrl = ENV.NEXT_PUBLIC_API_URL;

    if (!apiUrl || apiUrl === 'http://localhost:8000') {
        console.warn('⚠️ Using default localhost URL. If in Azure, check build args.');
    }

    return {
        name: "Mobile Contract Agent",
        url: apiUrl,
        version: "1.0.0",
        description: "Default agent for mobile contract analysis",
        capabilities: {
            streaming: true,
            pushNotifications: false,
            stateTransitionHistory: false
        },
        defaultInputModes: ["application/json", "text/plain"],
        defaultOutputModes: ["application/json", "text/plain"],
        skills: []
    };
};

const loadAgentsFromStorage = (): HostState => {
    try {
        if (typeof window !== 'undefined') {
            const stored = localStorage.getItem(AGENTS_STORAGE_KEY);
            if (stored) {
                const hosts = JSON.parse(stored);
                // Only use stored agents if there's at least one valid agent
                if (Array.isArray(hosts) && hosts.length > 0) {
                    return new HostState({ hosts });
                }
            }
        }
    } catch (error) {
        console.error("Failed to load agents from localStorage:", error);
    }

    // Return HostState with default agent if localStorage is empty or invalid
    console.log("Initializing default agent from ENV.NEXT_PUBLIC_API_URL:", ENV.NEXT_PUBLIC_API_URL);
    return new HostState({ hosts: [createDefaultAgent()] });
};

// Define the shape of the context
interface HostStateContextType {
    hostState: HostState;
    setHostState: React.Dispatch<React.SetStateAction<HostState>>;
    saveAgents: () => void;
    isLoaded: boolean;
}

// Create the context with a default value of undefined.
// You will validate that the context is defined in the hook.
const HostStateContext = createContext<HostStateContextType | undefined>(undefined);

export const HostStateProvider = ({ children }: { children: ReactNode }) => {
    // Initialize with empty state to prevent hydration mismatch
    const [hostState, setHostState] = useState<HostState>(() => new HostState());
    const [isLoaded, setIsLoaded] = useState(false);

    // Load from localStorage on client side only
    useEffect(() => {
        const loadedState = loadAgentsFromStorage();
        setHostState(loadedState);
        setIsLoaded(true);
    }, []);

    // Save to localStorage whenever hostState changes (but only after initial load)
    useEffect(() => {
        if (isLoaded) {
            saveAgentsToStorage(hostState);
        }
    }, [hostState, isLoaded]);

    // Manual save function
    const saveAgents = () => {
        saveAgentsToStorage(hostState);
    };

    return (
        <HostStateContext.Provider value={{ hostState, setHostState, saveAgents, isLoaded }}>
            {children}
        </HostStateContext.Provider>
    );
};

// Custom hook for consuming the context.
export const useHostState = (): HostStateContextType => {
    const context = useContext(HostStateContext);
    if (!context) {
        throw new Error("useHostState must be used within an HostStateProvider");
    }
    return context;
};