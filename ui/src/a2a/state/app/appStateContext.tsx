"use client";

import React, { createContext, useContext, useState, ReactNode, useEffect } from "react";
import {AppState} from "@/a2a/state/app/AppState";

// Constants for localStorage
const APP_STATE_STORAGE_KEY = "a2a_app_state";

// Utility functions for localStorage
const saveAppStateToStorage = (appState: AppState) => {
    try {
        if (typeof window !== 'undefined') {
            localStorage.setItem(APP_STATE_STORAGE_KEY, JSON.stringify(appState));
        }
    } catch (error) {
        console.error("Failed to save app state to localStorage:", error);
    }
};

const loadAppStateFromStorage = (): AppState => {
    try {
        if (typeof window !== 'undefined') {
            const stored = localStorage.getItem(APP_STATE_STORAGE_KEY);
            if (stored) {
                const data = JSON.parse(stored);
                return new AppState(data);
            }
        }
    } catch (error) {
        console.error("Failed to load app state from localStorage:", error);
    }
    return new AppState();
};

// Define the shape of the context
interface AppStateContextType {
    appState: AppState;
    setAppState: React.Dispatch<React.SetStateAction<AppState>>;
    saveAppState: () => void;
    isLoaded: boolean;
}

// Create the context with a default value of undefined.
// You will validate that the context is defined in the hook.
const AppStateContext = createContext<AppStateContextType | undefined>(undefined);

export const AppStateProvider = ({ children }: { children: ReactNode }) => {
    // Initialize with empty state to prevent hydration mismatch
    const [appState, setAppState] = useState<AppState>(() => new AppState());
    const [isLoaded, setIsLoaded] = useState(false);

    // Load from localStorage on client side only
    useEffect(() => {
        const loadedState = loadAppStateFromStorage();
        setAppState(loadedState);
        setIsLoaded(true);
    }, []);

    // Save to localStorage whenever appState changes (but only after initial load)
    useEffect(() => {
        if (isLoaded) {
            saveAppStateToStorage(appState);
        }
    }, [appState, isLoaded]);

    // Manual save function
    const saveAppState = () => {
        saveAppStateToStorage(appState);
    };

    return (
        <AppStateContext.Provider value={{ appState, setAppState, saveAppState, isLoaded }}>
            {children}
        </AppStateContext.Provider>
    );
};

// Custom hook for consuming the context.
export const useAppState = (): AppStateContextType => {
    const context = useContext(AppStateContext);
    if (!context) {
        throw new Error("useAppState must be used within an AppStateProvider");
    }
    return context;
};
