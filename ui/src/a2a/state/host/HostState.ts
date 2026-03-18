import {AgentCard} from "@/a2a/schema";

interface AgentList extends Array<AgentCard> {
    first: AgentCard | null;
}

export class HostState {
    hosts: AgentCard[] = [];

    constructor(init?: Partial<HostState>) {
        if (init) {
            Object.assign(this, init);
        }
    }

    // Alias for compatibility with existing code
    get agents(): AgentList {
        const agentArray = [...this.hosts] as AgentList;
        agentArray.first = this.hosts[0] || null;
        return agentArray;
    }

    set agents(value: AgentCard[]) {
        this.hosts = value;
    }
}
