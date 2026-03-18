import { useState, useEffect, useCallback } from 'react';

/**
 * Custom hook for managing localStorage with automatic serialization/deserialization
 * @param key - The localStorage key
 * @param defaultValue - Default value if nothing is stored
 * @returns [value, setValue, removeValue]
 */
export function useLocalStorage<T>(key: string, defaultValue: T) {
    // State to store our value
    const [storedValue, setStoredValue] = useState<T>(defaultValue);
    const [isLoaded, setIsLoaded] = useState(false);

    // Load value from localStorage on mount
    useEffect(() => {
        try {
            const item = window.localStorage.getItem(key);
            if (item) {
                const parsedValue = JSON.parse(item);
                setStoredValue(parsedValue);
            }
        } catch (error) {
            console.error(`Error loading localStorage key "${key}":`, error);
        } finally {
            setIsLoaded(true);
        }
    }, [key]);

    // Return a wrapped version of useState's setter function that persists the new value to localStorage
    const setValue = useCallback((value: T | ((val: T) => T)) => {
        try {
            // Allow value to be a function so we have the same API as useState
            const valueToStore = value instanceof Function ? value(storedValue) : value;

            // Save state
            setStoredValue(valueToStore);

            // Save to localStorage
            if (isLoaded) {
                window.localStorage.setItem(key, JSON.stringify(valueToStore));
            }
        } catch (error) {
            console.error(`Error setting localStorage key "${key}":`, error);
        }
    }, [key, storedValue, isLoaded]);

    // Function to remove the value from localStorage
    const removeValue = useCallback(() => {
        try {
            window.localStorage.removeItem(key);
            setStoredValue(defaultValue);
        } catch (error) {
            console.error(`Error removing localStorage key "${key}":`, error);
        }
    }, [key, defaultValue]);

    return [storedValue, setValue, removeValue, isLoaded] as const;
}
