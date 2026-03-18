import React, { useCallback, useRef } from "react";
import { X, File, FileText, Image as ImageIcon, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface FileAttachment {
    file: File;
    name: string;
    type: string;
    size: number;
    preview?: string;
}

interface FileUploadProps {
    files: FileAttachment[];
    onFilesSelected: (files: FileAttachment[]) => void;
    onFileRemove: (index: number) => void;
    maxFiles?: number;
    maxSizeMB?: number;
    accept?: string;
    disabled?: boolean;
}

export const FileUpload: React.FC<FileUploadProps> = ({
    files,
    onFilesSelected,
    onFileRemove,
    maxFiles = 10,
    maxSizeMB = 50,
    accept = "*/*",
    disabled = false,
}) => {
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [dragActive, setDragActive] = React.useState(false);

    const formatFileSize = (bytes: number): string => {
        if (bytes === 0) return "0 Bytes";
        const k = 1024;
        const sizes = ["Bytes", "KB", "MB", "GB"];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
    };

    const processFiles = useCallback(
        async (fileList: FileList | null) => {
            if (!fileList || disabled) return;

            const newFiles: FileAttachment[] = [];
            const maxSizeBytes = maxSizeMB * 1024 * 1024;

            for (let i = 0; i < fileList.length; i++) {
                const file = fileList[i];

                // Check file size
                if (file.size > maxSizeBytes) {
                    alert(
                        `File "${file.name}" is too large. Maximum size is ${maxSizeMB}MB.`
                    );
                    continue;
                }

                // Check max files limit
                if (files.length + newFiles.length >= maxFiles) {
                    alert(`Maximum ${maxFiles} files allowed.`);
                    break;
                }

                const attachment: FileAttachment = {
                    file,
                    name: file.name,
                    type: file.type,
                    size: file.size,
                };

                // Generate preview for images
                if (file.type.startsWith("image/")) {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        attachment.preview = e.target?.result as string;
                    };
                    reader.readAsDataURL(file);
                }

                newFiles.push(attachment);
            }

            if (newFiles.length > 0) {
                onFilesSelected([...files, ...newFiles]);
            }
        },
        [files, maxFiles, maxSizeMB, disabled, onFilesSelected]
    );

    const handleDrag = useCallback((e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            e.stopPropagation();
            setDragActive(false);
            if (!disabled) {
                processFiles(e.dataTransfer.files);
            }
        },
        [disabled, processFiles]
    );

    const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
        processFiles(e.target.files);
        // Reset input
        if (fileInputRef.current) {
            fileInputRef.current.value = "";
        }
    };

    const getFileIcon = (type: string) => {
        if (type.startsWith("image/")) return <ImageIcon className="h-4 w-4" />;
        if (type.includes("text")) return <FileText className="h-4 w-4" />;
        return <File className="h-4 w-4" />;
    };

    return (
        <div className="space-y-3">
            {/* Upload Area */}
            <div
                onDragEnter={handleDrag}
                onDragLeave={handleDrag}
                onDragOver={handleDrag}
                onDrop={handleDrop}
                className={`border-2 border-dashed rounded-lg p-6 text-center transition-colors ${
                    dragActive
                        ? "border-primary bg-primary/5"
                        : "border-border bg-background"
                } ${disabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:border-primary/50"}`}
                onClick={() => !disabled && fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    multiple
                    accept={accept}
                    onChange={handleFileInput}
                    disabled={disabled}
                    className="hidden"
                />
                <Upload className="h-8 w-8 mx-auto mb-2 text-muted-foreground" />
                <p className="text-sm text-foreground font-medium">
                    Drop files here or click to browse
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                    Max {maxFiles} files, {maxSizeMB}MB each
                </p>
            </div>

            {/* File List */}
            {files.length > 0 && (
                <div className="space-y-2 max-h-64 overflow-y-auto">
                    {files.map((attachment, index) => (
                        <div
                            key={index}
                            className="flex items-center gap-3 p-3 bg-muted rounded-lg border border-border"
                        >
                            {/* File Icon/Preview */}
                            <div className="flex-shrink-0">
                                {attachment.preview ? (
                                    <img
                                        src={attachment.preview}
                                        alt={attachment.name}
                                        className="h-10 w-10 object-cover rounded"
                                    />
                                ) : (
                                    <div className="h-10 w-10 bg-background rounded flex items-center justify-center text-muted-foreground">
                                        {getFileIcon(attachment.type)}
                                    </div>
                                )}
                            </div>

                            {/* File Info */}
                            <div className="flex-1 min-w-0">
                                <p className="text-sm font-medium text-foreground truncate">
                                    {attachment.name}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {formatFileSize(attachment.size)}
                                </p>
                            </div>

                            {/* Remove Button */}
                            <Button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onFileRemove(index);
                                }}
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8 flex-shrink-0"
                                disabled={disabled}
                            >
                                <X className="h-4 w-4" />
                            </Button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};
