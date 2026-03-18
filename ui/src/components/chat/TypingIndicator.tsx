import React from "react";

export const TypingIndicator: React.FC = () => {
    return (
        <div className="mb-4 flex flex-col items-start">
            {/* Sender name */}
            <div className="text-xs text-muted-foreground mb-1 px-2 text-left">
                Assistant
            </div>

            {/* Loading bubble */}
            <div className="relative max-w-[70%] px-4 py-3 rounded-2xl bg-muted text-foreground rounded-bl-md">
                <div className="flex items-center space-x-2">
                    <div className="flex space-x-1">
                        <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{animationDelay: '0ms'}}></div>
                        <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{animationDelay: '150ms'}}></div>
                        <div className="w-2 h-2 bg-muted-foreground/60 rounded-full animate-bounce" style={{animationDelay: '300ms'}}></div>
                    </div>
                    <span className="text-muted-foreground text-sm">Thinking...</span>
                </div>
            </div>
        </div>
    );
};
