import { Artifact, Part } from "@/a2a/schema";

export interface ChatMessage {
    id: number;
    sender: "agent" | "user";
    content: string;
    senderName: string;
    timestamp: Date;
    artifacts?: Artifact[];
    parts?: Part[];
}

export type TabType = "chat" | "chats";
