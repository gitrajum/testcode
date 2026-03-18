import {Badge} from "@/components/ui/badge"
import {Card, CardContent} from "@/components/ui/card"
import {useAgentState} from "@/a2a/state/agent/agentStateContext";
import {useAppState} from "@/a2a/state/app/appStateContext";
import {Button} from "@/components/ui/button";
import React from "react";
import { ENV } from "@/lib/env";
import {v4 as uuidv4} from "uuid";
import {StateConversation} from "@/a2a/state";
import {ExternalLink, LucideSidebar, Pencil, Trash2} from "lucide-react";
import {Input} from "@/components/ui/input";
import {A2AClient} from "@/a2a/client";
import {AgentCard} from "@/a2a/schema";
import {useHostState} from "@/a2a/state/host/hostStateContext";

export default function AgentListPage() {
    const agentUrl = ENV.NEXT_PUBLIC_API_URL;
    const agentName = "Default Agent";
    return (
        <div>
            <div className="flex items-center justify-between mb-8">
                <div>
                    <h2 className="text-2xl font-semibold text-foreground">Agent</h2>
                    <p className="text-muted-foreground">
                        This is the only agent available for this application.
                    </p>
                </div>
            </div>
            <Card className="py-3 px-6">
                <CardContent className="p-0 flex justify-between items-center text-sm">
                    <div>
                        <div className="font-medium text-lg text-foreground">{agentName}</div>
                        <div className="text-md text-muted-foreground">URL: {agentUrl}</div>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
