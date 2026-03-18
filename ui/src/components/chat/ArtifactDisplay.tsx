import React from "react";
import { Artifact, Part } from "@/a2a/schema";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileText, Database, Download } from "lucide-react";
import { MarkdownRenderer } from "@/components/common/MarkdownRenderer";
import { ExportMarkdownButton } from "@/components/common/ExportMarkdownButton";

interface ArtifactDisplayProps {
    artifact: Artifact;
}

interface PartDisplayProps {
    part: Part;
    index: number;
}

const PartDisplay: React.FC<PartDisplayProps> = ({ part, index }) => {
    switch (part.kind) {
        case "text":
            return (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <FileText className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Text Part {index + 1}</span>
                    </div>
                    <div className="bg-muted/50 rounded-md p-3">
                        <MarkdownRenderer content={part.text} compact={false} />
                    </div>
                    {part.metadata && Object.keys(part.metadata).length > 0 && (
                        <div className="text-xs text-muted-foreground">
                            <strong>Metadata:</strong> {JSON.stringify(part.metadata, null, 2)}
                        </div>
                    )}
                </div>
            );

        case "file":
            return (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <Download className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">File Part {index + 1}</span>
                    </div>
                    <div className="bg-muted/50 rounded-md p-3">
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
                                File content available as base64 data ({part.file.bytes.length} chars)
                            </div>
                        )}
                    </div>
                    {part.metadata && Object.keys(part.metadata).length > 0 && (
                        <div className="text-xs text-muted-foreground">
                            <strong>Metadata:</strong> {JSON.stringify(part.metadata, null, 2)}
                        </div>
                    )}
                </div>
            );

        case "data":
            return (
                <div className="space-y-2">
                    <div className="flex items-center gap-2">
                        <Database className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm font-medium">Data Part {index + 1}</span>
                    </div>
                    <div className="bg-muted/50 rounded-md p-3">
                        <pre className="text-xs whitespace-pre-wrap break-words">
                            {JSON.stringify(part.data, null, 2)}
                        </pre>
                    </div>
                    {part.metadata && Object.keys(part.metadata).length > 0 && (
                        <div className="text-xs text-muted-foreground">
                            <strong>Metadata:</strong> {JSON.stringify(part.metadata, null, 2)}
                        </div>
                    )}
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

export const ArtifactDisplay: React.FC<ArtifactDisplayProps> = ({ artifact }) => {
    // Extract all text content from parts for full export
    const fullMarkdownContent = artifact.parts
        .filter(part => part.kind === "text")
        .map(part => part.text)
        .join('\n\n---\n\n');

    // Detect if this is a phase artifact
    const isPhaseArtifact = artifact.name?.toLowerCase().includes('phase') || false;
    const borderColor = isPhaseArtifact ? 'border-l-green-500' : 'border-l-blue-500';

    return (
        <Card className={`mt-2 border-l-4 ${borderColor}`}>
            <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 flex-1 min-w-0">
                        <CardTitle className="text-sm truncate">
                            {artifact.name || `Artifact ${artifact.artifactId}`}
                        </CardTitle>
                        <Badge variant="secondary" className="text-xs shrink-0">
                            {artifact.parts.length} part{artifact.parts.length !== 1 ? "s" : ""}
                        </Badge>
                    </div>
                    {fullMarkdownContent && (
                        <div className="shrink-0">
                            <ExportMarkdownButton
                                markdown={fullMarkdownContent}
                                filename={artifact.name || `artifact-${artifact.artifactId}`}
                                variant="outline"
                                size="sm"
                            />
                        </div>
                    )}
                </div>
                {artifact.description && (
                    <CardDescription className="text-xs">
                        {artifact.description}
                    </CardDescription>
                )}
                {artifact.extensions && artifact.extensions.length > 0 && (
                    <div className="flex gap-1 flex-wrap">
                        {artifact.extensions.map((ext, index) => (
                            <Badge key={index} variant="outline" className="text-xs">
                                {ext}
                            </Badge>
                        ))}
                    </div>
                )}
            </CardHeader>
            <CardContent className="space-y-4">
                {artifact.parts.map((part, index) => (
                    <PartDisplay key={index} part={part} index={index} />
                ))}
                {artifact.metadata && Object.keys(artifact.metadata).length > 0 && (
                    <div className="text-xs text-muted-foreground border-t pt-2">
                        <strong>Artifact Metadata:</strong>
                        <pre className="mt-1 whitespace-pre-wrap">
                            {JSON.stringify(artifact.metadata, null, 2)}
                        </pre>
                    </div>
                )}
            </CardContent>
        </Card>
    );
};
