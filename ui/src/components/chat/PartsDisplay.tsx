import React from "react";
import { Part } from "@/a2a/schema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { FileText, Database, Download } from "lucide-react";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";

interface PartsDisplayProps {
    parts: Part[];
}

interface PartItemProps {
    part: Part;
    index: number;
}

const PartItem: React.FC<PartItemProps> = ({ part, index }) => {
    const getPartIcon = (kind: string) => {
        switch (kind) {
            case "text":
                return <FileText className="h-4 w-4" />;
            case "file":
                return <Download className="h-4 w-4" />;
            case "data":
                return <Database className="h-4 w-4" />;
            default:
                return <div className="h-4 w-4 bg-muted rounded" />;
        }
    };

    const getPartTitle = (kind: string) => {
        switch (kind) {
            case "text":
                return "Text";
            case "file":
                return "File";
            case "data":
                return "Data";
            default:
                return "Unknown";
        }
    };

    const renderPartContent = () => {
        switch (part.kind) {
            case "text":
                return (
                    <div className="bg-muted/50 rounded-md p-3">
                        <MarkdownRenderer content={part.text || ""} compact={true} />
                    </div>
                );

            case "file":
                return (
                    <div className="bg-muted/30 rounded-md p-3 space-y-2">
                        <div className="text-sm">
                            <strong>Name:</strong> {part.file.name || "Untitled file"}
                        </div>
                        {part.file.mimeType && (
                            <div className="text-sm">
                                <strong>Type:</strong> {part.file.mimeType}
                            </div>
                        )}
                        {"uri" in part.file ? (
                            <div className="text-sm">
                                <strong>URL:</strong>{" "}
                                <a
                                    href={part.file.uri}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="text-primary hover:underline"
                                >
                                    {part.file.uri}
                                </a>
                            </div>
                        ) : (
                            <div className="text-sm text-muted-foreground">
                                Base64 data ({part.file.bytes.length} chars)
                            </div>
                        )}
                    </div>
                );

            case "data":
                return (
                    <div className="bg-muted/30 rounded-md p-3">
                        <pre className="text-xs whitespace-pre-wrap break-words">
                            {JSON.stringify(part.data, null, 2)}
                        </pre>
                    </div>
                );

            default:
                return (
                    <div className="text-sm text-muted-foreground">
                        Unknown part type: {(part as any).kind}
                    </div>
                );
        }
    };

    return (
        <Card className="border-l-4 border-l-green-500">
            <CardHeader className="pb-2">
                <CardTitle className="text-sm flex items-center gap-2">
                    {getPartIcon(part.kind)}
                    {getPartTitle(part.kind)} Part {index + 1}
                </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
                {renderPartContent()}
                {part.metadata && Object.keys(part.metadata).length > 0 && (
                    <div className="text-xs text-muted-foreground border-t pt-2">
                        <strong>Metadata:</strong>
                        <pre className="mt-1 whitespace-pre-wrap">
                            {JSON.stringify(part.metadata, null, 2)}
                        </pre>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};

export const PartsDisplay: React.FC<PartsDisplayProps> = ({ parts }) => {
    if (!parts || parts.length === 0) {
        return null;
    }

    return (
        <div className="mt-2 space-y-2">
            {parts.map((part, index) => (
                <PartItem key={index} part={part} index={index} />
            ))}
        </div>
    );
};
