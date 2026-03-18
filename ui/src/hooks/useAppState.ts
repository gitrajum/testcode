import { useState, useEffect } from "react";
import { TabType } from "@/types/chat";
import { AgentCard } from "@/a2a/schema";
import { StateConversation } from "@/a2a/state";
import { useHostState } from "@/a2a/state/host/hostStateContext";

export const useAppState = () => {
    const [activeTab, setActiveTab] = useState<TabType>("chats");
    const [showAgentDetails, setShowAgentDetails] = useState(true);
    const [selectedAgent, setSelectedAgent] = useState<AgentCard | null>(null);
    const [conversation, setConversation] = useState<StateConversation | null>(null);

    const { hostState, isLoaded: hostStateLoaded } = useHostState();

    // Set selected agent from hostState when available and loaded
    useEffect(() => {
        if (hostStateLoaded && !selectedAgent && hostState.agents.first) {
            console.log('Setting default agent from hostState:', hostState.agents.first);
            setSelectedAgent(hostState.agents.first);
        }
    }, [hostStateLoaded, hostState.agents.first, selectedAgent]);

    const handleTabChange = (tab: TabType) => {
        setActiveTab(tab);
    };

    const handleOpenConversation = (conversation: StateConversation) => {
        setConversation(conversation);

        // Автоматически выбираем агента для этого разговора
        if (conversation.agent_url && hostStateLoaded) {
            const conversationAgent = hostState.agents.find(agent => agent.url === conversation.agent_url);
            if (conversationAgent) {
                setSelectedAgent(conversationAgent);
            }
        }

        setActiveTab("chat");
    };

    return {
        activeTab,
        showAgentDetails,
        selectedAgent,
        conversation,
        handleTabChange,
        handleOpenConversation,
        setShowAgentDetails,
        setSelectedAgent,
        setConversation
    };
};