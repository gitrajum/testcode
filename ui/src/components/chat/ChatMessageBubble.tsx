import React from "react";
import { ChatMessage } from "@/types/chat";
import { ArtifactDisplay } from "./ArtifactDisplay";
import { PartsDisplay } from "./PartsDisplay";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";
import { ExportMarkdownButton } from "@/components/common/ExportMarkdownButton";

interface ChatMessageBubbleProps {
    message: ChatMessage;
}

export const ChatMessageBubble: React.FC<ChatMessageBubbleProps> = ({ message }) => {
    // Generate a smart filename based on message content
    const generateFilename = () => {
        // Check if message contains phase information
        const phaseMatch = message.content?.match(/#{1,3}\s*(Phase\s+\d+[^#\n]*)/i);
        if (phaseMatch) {
            return phaseMatch[1].trim().toLowerCase().replace(/[^a-z0-9]+/g, '-');
        }

        // Check artifacts for phase names
        if (message.artifacts && message.artifacts.length > 0) {
            const phaseArtifact = message.artifacts.find(a => a.name?.toLowerCase().includes('phase'));
            if (phaseArtifact?.name) {
                return phaseArtifact.name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
            }
        }

        // Default fallback
        return `agent-response-${message.id}`;
    };

    return (
        <div
            className={`mb-4 ${
                message.sender === "user" ? "flex flex-col items-end" : "flex flex-col items-start"
            }`}
        >
            {/* Sender name */}
            <div className={`text-xs text-muted-foreground mb-1 px-2 ${
                message.sender === "user" ? "text-right" : "text-left"
            }`}>
                {message.senderName}
            </div>

            <div className="max-w-[70%] space-y-2">
                {/* Export button for agent messages - only show if no artifacts */}
                {message.sender === "agent" && message.content && (!message.artifacts || message.artifacts.length === 0) && (
                    <div className="flex justify-end mb-2">
                        <ExportMarkdownButton
                            markdown={message.content}
                            filename={generateFilename()}
                            variant="outline"
                            size="sm"
                        />
                    </div>
                )}

                {/* Message bubble */}
                {message.content && (
                    <div className={`relative px-4 py-3 rounded-2xl text-sm break-words ${
                        message.sender === "user"
                            ? "bg-primary text-primary-foreground rounded-br-md"
                            : "bg-muted text-foreground rounded-bl-md"
                    }`}>
                        {message.sender === "agent" ? (
                            <MarkdownRenderer content={message.content} compact={true} />
                        ) : (
                            <div className="whitespace-pre-wrap">{message.content}</div>
                        )}

                        {/* Timestamp */}
                        <div className={`text-xs mt-1 ${
                            message.sender === "user" ? "text-primary-foreground/70" : "text-muted-foreground"
                        }`}>
                            {message.timestamp.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
                        </div>
                    </div>
                )}

                {/* Artifacts */}
                {message.artifacts && message.artifacts.length > 0 && (
                    <div className="space-y-2">
                        {message.artifacts.map((artifact, index) => (
                            <ArtifactDisplay key={artifact.artifactId || index} artifact={artifact} />
                        ))}
                    </div>
                )}

                {/* Parts */}
                {message.parts && message.parts.length > 0 && (
                    <PartsDisplay parts={message.parts.filter(p => p.kind !== "text")} />
                )}
            </div>
        </div>
    );
};
