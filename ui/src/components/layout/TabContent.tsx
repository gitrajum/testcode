import React from "react";
import { TabType } from "@/types/chat";
import { AgentCard } from "@/a2a/schema";
import { StateConversation } from "@/a2a/state";
import { ChatContainer } from "@/components/chat/ChatContainer";
import WorkflowPage from "@/app/pages/WorkflowPage";
import ConversationListPage from "@/app/pages/ConversationListPage";
// import AgentListPage removed
// import EventListPage removed
// import TaskListPage removed
// import SettingsPage removed
import { useAuth } from "@/hooks/useAuth";

interface TabContentProps {
    activeTab: TabType;
    selectedAgent: AgentCard | null;
    showAgentDetails: boolean;
    conversation: StateConversation | null;
    onChatTabChange?: () => void;
    onOpenConversation: (conversation: StateConversation) => void;
}

export const TabContent: React.FC<TabContentProps> = ({
    selectedAgent,
    conversation
}) => {
    const { getAccessToken } = useAuth();
    return (
        <main className="flex-1 overflow-hidden min-h-0">
            <WorkflowPage
                selectedAgent={selectedAgent}
                getAccessToken={getAccessToken}
            />
        </main>
    );
};
