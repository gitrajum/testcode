"use client";

import React, { createContext, useContext, useState, ReactNode, useEffect, useRef } from "react";
import {SettingsState} from "@/a2a/state/settings/SettingsState";
import { useLocalStorage } from "@/hooks/useLocalStorage";

// Define the shape of the context
interface SettingStateContextType {
    settingsState: SettingsState;
    setSettingsState: React.Dispatch<React.SetStateAction<SettingsState>>;
    saveSettings: () => void;
    loadSettings: () => void;
    resetSettings: () => void;
    isLoaded: boolean;
}

// Create the context with a default value of undefined.
// You will validate that the context is defined in the hook.
const SettingsStateContext = createContext<SettingStateContextType | undefined>(undefined);

const SETTINGS_STORAGE_KEY = 'a2a-ui-settings';

// Default settings
const defaultSettings = new SettingsState();

export const SettingsStateProvider = ({ children }: { children: ReactNode }) => {
    // Use our custom localStorage hook
    const [storedSettings, setStoredSettings, removeStoredSettings, isLoaded] = useLocalStorage(
        SETTINGS_STORAGE_KEY,
        defaultSettings
    );

    // Create the SettingsState using React's useState hook, initialized from localStorage
    const [settingsState, setSettingsState] = useState<SettingsState>(defaultSettings);

    // Track if we've initialized from localStorage to prevent cycles
    const hasInitialized = useRef(false);

    // Initialize settingsState from localStorage only once when loaded
    useEffect(() => {
        if (isLoaded && !hasInitialized.current) {
            if (storedSettings) {
                setSettingsState(new SettingsState(storedSettings));
            }
            hasInitialized.current = true;
        }
    }, [isLoaded, storedSettings]);

    // Custom setSettingsState that also saves to localStorage
    const setSettingsStateWithSave = (value: SettingsState | ((prev: SettingsState) => SettingsState)) => {
        setSettingsState(prevState => {
            const newState = typeof value === 'function' ? value(prevState) : value;

            // Save to localStorage if initialized
            if (hasInitialized.current && isLoaded) {
                setStoredSettings(newState);
            }

            return newState;
        });
    };

    const saveSettings = () => {
        if (isLoaded) {
            setStoredSettings(settingsState);
            console.log('Settings manually saved to localStorage');
        }
    };

    const loadSettings = () => {
        if (storedSettings && isLoaded) {
            setSettingsState(new SettingsState(storedSettings));
            console.log('Settings reloaded from localStorage');
        }
    };

    const resetSettings = () => {
        const newSettings = new SettingsState();
        setSettingsState(newSettings);
        if (isLoaded) {
            setStoredSettings(newSettings);
        }
        console.log('Settings reset to defaults');
    };

    return (
        <SettingsStateContext.Provider value={{
            settingsState,
            setSettingsState: setSettingsStateWithSave,
            saveSettings,
            loadSettings,
            resetSettings,
            isLoaded: isLoaded && hasInitialized.current
        }}>
            {children}
        </SettingsStateContext.Provider>
    );
};

// Custom hook for consuming the context.
export const useSettingsState = (): SettingStateContextType => {
    const context = useContext(SettingsStateContext);
    if (!context) {
        throw new Error("useSettingsState must be used within an SettingsStateProvider");
    }
    return context;
};
