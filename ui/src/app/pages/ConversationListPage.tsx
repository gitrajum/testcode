import {Badge} from "@/components/ui/badge"
import {Card, CardContent} from "@/components/ui/card"
import {useAgentState} from "@/a2a/state/agent/agentStateContext";
import {useAppState} from "@/a2a/state/app/appStateContext";
import {Button} from "@/components/ui/button";
import {Input} from "@/components/ui/input";
import React, { useState } from "react";
import {v4 as uuidv4} from "uuid";
import {StateConversation} from "@/a2a/state";
import {ExternalLink, Pencil, Trash2} from "lucide-react";
import {useHostState} from "@/a2a/state/host/hostStateContext";

type Props = {
    openConversation: (conversation: StateConversation) => void;
};
export default function ConversationListPage({openConversation}: Props) {
    const {agentState, setAgentState} = useAgentState();
    const {appState, setAppState, isLoaded: appStateLoaded} = useAppState();
    const {hostState, isLoaded: hostStateLoaded} = useHostState();

    React.useEffect(() => {
        if (appStateLoaded && hostStateLoaded && appState.conversations.length === 0 && hostState.agents.length > 0) {
            const defaultAgent = hostState.agents[0];
            const newConversation = new StateConversation(
                uuidv4(),
                "Default Conversation",
                true,
                [],
                defaultAgent.url,
                uuidv4()
            );
            setAppState({
                ...appState,
                conversations: [newConversation],
            });
        }
    }, [appStateLoaded, hostStateLoaded, appState.conversations.length, hostState.agents.length]);

    // State for delete confirmation modal
    const [showDeleteModal, setShowDeleteModal] = useState(false);
    const [conversationToDelete, setConversationToDelete] = useState<{id: string, name: string} | null>(null);

    // State for new conversation modal
    const [showNewConversationModal, setShowNewConversationModal] = useState(false);
    const [newConversationName, setNewConversationName] = useState("New conversation");
    const [selectedAgentUrl, setSelectedAgentUrl] = useState<string>("");

    // Handler for opening delete confirmation modal
    const handleDeleteConversation = (conversationId: string, conversationName: string) => {
        setConversationToDelete({ id: conversationId, name: conversationName });
        setShowDeleteModal(true);
    };

    // Handler for confirming deletion
    const confirmDeleteConversation = () => {
        if (!conversationToDelete) return;

        try {
            const updatedConversations = appState.conversations.filter(
                conv => conv.conversation_id !== conversationToDelete.id
            );

            setAppState({
                ...appState,
                conversations: updatedConversations,
            });

            console.log(`Conversation "${conversationToDelete.name}" successfully deleted and removed from localStorage`);
            alert(`Conversation "${conversationToDelete.name}" has been successfully deleted.`);

            // Close modal and reset state
            setShowDeleteModal(false);
            setConversationToDelete(null);
        } catch (error) {
            console.error("Error deleting conversation:", error);
            alert("Failed to delete conversation. Please try again.");
        }
    };

    // Handler for canceling deletion
    const cancelDeleteConversation = () => {
        setShowDeleteModal(false);
        setConversationToDelete(null);
    };

    // Handler for creating new conversation
    const handleCreateConversation = () => {
        setShowNewConversationModal(true);
        // Set first agent as default if available
        if (hostState.agents.length > 0) {
            setSelectedAgentUrl(hostState.agents[0].url);
        }
    };

    // Handler for confirming conversation creation
    const confirmCreateConversation = () => {
        try {
            if (!selectedAgentUrl) {
                alert("Please select an agent for this conversation.");
                return;
            }

            const newConversation = new StateConversation(
                uuidv4(),
                newConversationName.trim() || "New conversation",
                true,
                [],
                selectedAgentUrl,
                uuidv4() // Generate unique contextId for A2A protocol
            );

            const updatedConversations = [
                ...appState.conversations,
                newConversation,
            ];

            setAppState({
                ...appState,
                conversations: updatedConversations,
            });

            console.log("New conversation created and saved to localStorage:", newConversation.conversation_name);
            alert("New conversation created successfully!");

            // Reset form and close modal
            setNewConversationName("New conversation");
            setSelectedAgentUrl("");
            setShowNewConversationModal(false);
        } catch (error) {
            console.error("Error creating conversation:", error);
            alert("Failed to create conversation. Please try again.");
        }
    };

    // Handler for canceling conversation creation
    const cancelCreateConversation = () => {
        setNewConversationName("New conversation");
        setSelectedAgentUrl("");
        setShowNewConversationModal(false);
    };

    // Show loading state until data is loaded
    if (!appStateLoaded || !hostStateLoaded) {
        return (
            <div className="flex items-center justify-center h-64">
                <div className="text-muted-foreground">Loading conversations...</div>
            </div>
        );
    }

    return (
        <div>
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-2xl font-semibold text-foreground">Conversations</h2>
                    <p className="text-muted-foreground">
                        This is the page where you can view your conversation with the default agent.
                    </p>
                </div>
            </div>
            <div className="space-y-4">
                {appState.conversations.length === 0 ? (
                    <div className="text-center py-12">
                        <p className="text-muted-foreground text-lg mb-4">Conversation started with default agent</p>
                        <p className="text-muted-foreground/60 text-sm">
                            You are now connected to the default agent.
                        </p>
                    </div>
                ) : (
                    appState.conversations.map(chat => (
                        <Card key={chat.conversation_id} className="py-3 px-6">

                        <CardContent className="p-0 flex justify-between items-center text-sm">
                            <div>
                                <div className="font-medium text-lg text-foreground">{chat.conversation_name}</div>
                                <div className="text-md text-muted-foreground">ID: {chat.conversation_id}</div>
                                {chat.context_id && (
                                    <div className="text-xs text-muted-foreground">Context ID: {chat.context_id}</div>
                                )}
                                {chat.agent_url && (
                                    <div className="text-sm text-primary">
                                        Agent: {hostState.agents.find(agent => agent.url === chat.agent_url)?.name || 'Unknown'}
                                    </div>
                                )}
                            </div>
                            <div className="flex items-center gap-3">
                                <Badge variant="outline" className="text-md">
                                    {chat.is_active ? "Active" : "Inactive"}
                                </Badge>
                                <div className="text-md text-muted-foreground">{chat.message_ids.length} messages</div>

                                {/* Buttons */}
                                <Button variant="ghost" size="icon"
                                        className="border ml-8 cursor-pointer"
                                        onClick={() => handleDeleteConversation(chat.conversation_id, chat.conversation_name)}>
                                    <Trash2 className="w-4 h-4 text-destructive"/>
                                </Button>
                                <Button variant="ghost" size="icon"
                                        className="border cursor-pointer">
                                    <Pencil className="w-4 h-4 text-muted-foreground"/>
                                </Button>
                                <Button variant="ghost" size="icon"
                                        className="border cursor-pointer" onClick={() => {
                                    openConversation(
                                        appState.conversations.find(
                                            it => it.conversation_id == chat.conversation_id
                                        )!
                                    );
                                }}>
                                    <ExternalLink className="w-4 h-4 text-muted-foreground"/>
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                    ))
                )}
            </div>

            {/* New Conversation Modal removed */}

            {/* Delete Conversation Confirmation Modal */}
            {showDeleteModal && conversationToDelete && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
                    <div className="bg-background border rounded-lg shadow-lg w-full max-w-md p-6 relative">
                        <h3 className="text-xl font-semibold mb-4 text-destructive">Delete Conversation</h3>
                        <div className="mb-6">
                            <p className="text-foreground">
                                Are you sure you want to delete conversation <strong>"{conversationToDelete.name}"</strong>?
                            </p>
                            <p className="text-sm text-muted-foreground mt-2">
                                This action cannot be undone. The conversation and all its messages will be permanently removed from your local storage.
                            </p>
                        </div>
                        <div className="flex justify-end space-x-2">
                            <Button variant="outline" onClick={cancelDeleteConversation}>
                                Cancel
                            </Button>
                            <Button variant="destructive" onClick={confirmDeleteConversation}>
                                Delete Conversation
                            </Button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
