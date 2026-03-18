import React, { useEffect } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessage } from "@/types/chat";
import { ChatMessageBubble } from "./ChatMessageBubble";
import { TypingIndicator } from "./TypingIndicator";

interface MessagesListProps {
    messages: ChatMessage[];
    isLoading: boolean;
    messagesEndRef: React.RefObject<HTMLDivElement | null>;
    scrollToBottom: () => void;
}

export const MessagesList: React.FC<MessagesListProps> = ({
    messages,
    isLoading,
    messagesEndRef,
    scrollToBottom
}) => {
    // Auto-scroll when messages change or loading state changes
    useEffect(() => {
        scrollToBottom();
    }, [messages, isLoading, scrollToBottom]);

    return (
        <ScrollArea className="h-full flex-1 px-6 py-4 overflow-hidden min-h-0">
            <div className="space-y-2">
                {messages.map((message) => (
                    <ChatMessageBubble key={message.id} message={message} />
                ))}

                {isLoading && <TypingIndicator />}

                <div ref={messagesEndRef} />
            </div>
        </ScrollArea>
    );
};
