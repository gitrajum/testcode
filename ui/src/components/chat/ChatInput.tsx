import React, { forwardRef, useEffect } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { ArrowUp } from "lucide-react";
import { FileUpload, FileAttachment } from "@/components/common/FileUpload";

interface ChatInputProps {
    value: string;
    onChange: (value: string) => void;
    onSend: () => void;
    onKeyDown: (e: React.KeyboardEvent) => void;
    disabled: boolean;
    placeholder?: string;
    files?: FileAttachment[];
    onFilesChange?: (files: FileAttachment[]) => void;
}

export const ChatInput = forwardRef<HTMLTextAreaElement, ChatInputProps>(({
    value,
    onChange,
    onSend,
    onKeyDown,
    disabled,
    placeholder = "Ask anything",
    files = [],
    onFilesChange
}, ref) => {
    // Auto-resize textarea
    useEffect(() => {
        if (ref && typeof ref === 'object' && ref.current) {
            const textarea = ref.current;
            textarea.style.height = '44px';
            const scrollHeight = textarea.scrollHeight;
            const maxHeight = 320; // max-h-80 = 20rem = 320px
            textarea.style.height = Math.min(scrollHeight, maxHeight) + 'px';
        }
    }, [value, ref]);

    const handleFilesSelected = (newFiles: FileAttachment[]) => {
        if (onFilesChange) {
            onFilesChange([...files, ...newFiles]);
        }
    };

    const handleFileRemove = (index: number) => {
        if (onFilesChange) {
            onFilesChange(files.filter((_, i) => i !== index));
        }
    };

    return (
        <div className="border-t border-border px-6 pt-6 pb-4 w-full">
            {onFilesChange && (
                <div className="mb-3">
                    <FileUpload
                        files={files}
                        onFilesSelected={handleFilesSelected}
                        onFileRemove={handleFileRemove}
                        maxFiles={10}
                        maxSizeMB={200}
                        disabled={disabled}
                    />
                </div>
            )}
            <div className="relative flex items-center gap-3">
                <Textarea
                    ref={ref}
                    placeholder={placeholder}
                    value={value}
                    onChange={(e) => onChange(e.target.value)}
                    onKeyDown={onKeyDown}
                    disabled={disabled}
                    className="flex-1 py-3 px-4 rounded-2xl shadow-sm resize-none focus-visible:ring-2 focus-visible:ring-primary/20 focus-visible:ring-offset-0 border-2 focus-visible:border-primary/30 min-h-[44px] max-h-80 disabled:opacity-50 bg-background text-foreground placeholder:text-muted-foreground transition-all duration-200"
                    rows={1}
                    style={{
                        minHeight: '44px',
                        height: 'auto',
                    }}
                />
                <Button
                    onClick={onSend}
                    disabled={disabled || (!value.trim() && files.length === 0)}
                    size="icon"
                    className="rounded-full h-11 w-11 p-0 cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0 bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg transition-all duration-200 hover:shadow-xl"
                >
                    <ArrowUp className="h-5 w-5"/>
                </Button>
            </div>
        </div>
    );
});

ChatInput.displayName = 'ChatInput';
