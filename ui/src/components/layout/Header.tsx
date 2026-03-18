import React from "react";
import { Button } from "@/components/ui/button";
import { TabType } from "@/types/chat";
import { ThemeToggle } from "@/components/ThemeToggle";
import { UserProfile } from "@/components/auth/UserProfile";

interface HeaderProps {
    activeTab: TabType;
    onTabChange: (tab: TabType) => void;
}

export const Header: React.FC<HeaderProps> = ({ activeTab, onTabChange }) => {
    // No navigation tabs shown

    return (
        <header className="bg-background border-b p-4 flex items-center justify-between">
            <h1 className="pl-12 text-xl font-bold text-foreground">Mobile Invoice Analyser UI</h1>

            <div className="flex items-center space-x-2 pr-12">
                <ThemeToggle />
                <UserProfile />
            </div>
        </header>
    );
};
