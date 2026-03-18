import React, { useState } from 'react';
import { useTrace } from '@/hooks/useTrace';
import { useSettingsState } from '@/a2a/state/settings/settingsStateContext';
import { JaegerTraceView } from './JaegerTraceView';
import { Search, RefreshCw, Database, AlertCircle, CheckCircle, Clock } from 'lucide-react';
import { AgentCard } from '@/a2a/schema';

export const TraceTestComponent: React.FC = () => {
    const [contextId, setContextId] = useState('84b99b80-f72d-4d09-9a7c-dfe78c98ba7c');
    const [selectedAgent, setSelectedAgent] = useState<AgentCard>({
        name: 'default-agent',
        url: 'http://localhost:8000',
        version: '1.0.0',
        capabilities: {
            streaming: true,
            pushNotifications: false,
            stateTransitionHistory: false
        },
        skills: []
    });
    const { settingsState } = useSettingsState();

    const { trace, loading, error, projectId, refreshTrace } = useTrace({
        contextId,
        settings: settingsState,
        selectedAgent,
        limit: 1000
    });

    const handleSearch = () => {
        refreshTrace();
    };

    const handleContextIdChange = (value: string) => {
        setContextId(value);
    };

    const handleAgentChange = (value: string) => {
        setSelectedAgent(prev => ({
            ...prev,
            name: value
        }));
    };

    return (
        <div className="w-full h-full flex flex-col bg-white">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 flex-shrink-0">
                <div className="flex items-center gap-4">
                    <Database className="h-6 w-6 text-blue-600" />
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">Trace Fetcher</h2>
                        <div className="text-sm text-gray-600">
                            Get traces by session_id from Phoenix
                        </div>
                    </div>
                </div>
            </div>

            {/* Controls */}
            <div className="p-4 border-b border-gray-200 bg-gray-50 flex-shrink-0">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {/* Context ID */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Session ID (Context ID)
                        </label>
                        <div className="relative">
                            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                            <input
                                type="text"
                                value={contextId}
                                onChange={(e) => handleContextIdChange(e.target.value)}
                                placeholder="Enter session ID..."
                                className="pl-10 pr-4 py-2 w-full border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                            />
                        </div>
                    </div>

                    {/* Agent Name */}
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-2">
                            Agent Name (Project)
                        </label>
                        <input
                            type="text"
                            value={selectedAgent.name}
                            onChange={(e) => handleAgentChange(e.target.value)}
                            placeholder="Enter agent name..."
                            className="px-4 py-2 w-full border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                    </div>

                    {/* Search Button */}
                    <div className="flex items-end">
                        <button
                            onClick={handleSearch}
                            disabled={loading || !contextId || !selectedAgent.name}
                            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
                        >
                            {loading ? (
                                <RefreshCw className="h-4 w-4 animate-spin" />
                            ) : (
                                <Search className="h-4 w-4" />
                            )}
                            {loading ? 'Searching...' : 'Search Traces'}
                        </button>
                    </div>
                </div>

                {/* Phoenix Settings Status */}
                <div className="mt-4 p-3 bg-white rounded-lg border">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <div className={`w-3 h-3 rounded-full ${
                                settingsState.arize_phoenix_enabled && settingsState.arize_phoenix_url
                                    ? 'bg-green-500'
                                    : 'bg-red-500'
                            }`} />
                            <span className="text-sm font-medium text-gray-700">
                                Phoenix Connection
                            </span>
                        </div>
                        <div className="text-sm text-gray-600">
                            {settingsState.arize_phoenix_enabled && settingsState.arize_phoenix_url
                                ? `Connected to ${settingsState.arize_phoenix_url}`
                                : 'Phoenix not configured'
                            }
                        </div>
                    </div>
                    {projectId && (
                        <div className="mt-2 text-xs text-gray-500">
                            Project ID: {projectId}
                        </div>
                    )}
                </div>
            </div>

            {/* Status */}
            <div className="p-4 border-b border-gray-200 flex-shrink-0">
                {loading && (
                    <div className="flex items-center gap-2 text-blue-600">
                        <RefreshCw className="h-4 w-4 animate-spin" />
                        <span className="text-sm">Fetching traces from Phoenix...</span>
                    </div>
                )}

                {error && (
                    <div className="flex items-center gap-2 text-red-600">
                        <AlertCircle className="h-4 w-4" />
                        <span className="text-sm">{error}</span>
                    </div>
                )}

                {trace && !loading && !error && (
                    <div className="flex items-center gap-2 text-green-600">
                        <CheckCircle className="h-4 w-4" />
                        <span className="text-sm">
                            Found {trace.length} spans for session: {contextId}
                        </span>
                    </div>
                )}

                {!trace && !loading && !error && contextId && (
                    <div className="flex items-center gap-2 text-gray-500">
                        <Clock className="h-4 w-4" />
                        <span className="text-sm">Ready to search traces</span>
                    </div>
                )}
            </div>

            {/* Results */}
            <div className="flex-1 min-h-0">
                {trace && trace.length > 0 ? (
                    <JaegerTraceView
                        trace={trace}
                        contextId={contextId}
                    />
                ) : !loading && !error && contextId ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500">
                        <Database className="h-16 w-16 mb-4 text-gray-300" />
                        <div className="text-center">
                            <div className="text-lg font-medium mb-2">No traces found</div>
                            <div className="text-sm">
                                No traces found for session ID: <code className="bg-gray-100 px-2 py-1 rounded">{contextId}</code>
                            </div>
                            <div className="text-xs text-gray-400 mt-2">
                                Make sure the session ID is correct and traces exist in Phoenix
                            </div>
                        </div>
                    </div>
                ) : !settingsState.arize_phoenix_enabled || !settingsState.arize_phoenix_url ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500">
                        <AlertCircle className="h-16 w-16 mb-4 text-gray-300" />
                        <div className="text-center">
                            <div className="text-lg font-medium mb-2">Phoenix not configured</div>
                            <div className="text-sm">
                                Please configure Phoenix settings to fetch traces
                            </div>
                        </div>
                    </div>
                ) : (
                    <div className="flex flex-col items-center justify-center h-full text-gray-500">
                        <Search className="h-16 w-16 mb-4 text-gray-300" />
                        <div className="text-center">
                            <div className="text-lg font-medium mb-2">Enter search criteria</div>
                            <div className="text-sm">
                                Enter a session ID and agent name to search for traces
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Debug Info */}
            {trace && trace.length > 0 && (
                <div className="border-t border-gray-200 p-4 bg-gray-50 flex-shrink-0">
                    <details className="text-sm">
                        <summary className="cursor-pointer font-medium text-gray-700 hover:text-gray-900">
                            Debug Information ({trace.length} spans)
                        </summary>
                        <div className="mt-2 space-y-2">
                            <div>
                                <strong>Trace IDs:</strong>
                                <div className="text-xs text-gray-600 mt-1">
                                    {Array.from(new Set(trace.map(span => span.context.trace_id)))
                                        .map(traceId => (
                                            <div key={traceId} className="font-mono">
                                                {traceId.substring(0, 16)}...
                                            </div>
                                        ))
                                    }
                                </div>
                            </div>
                            <div>
                                <strong>Session Spans:</strong>
                                <div className="text-xs text-gray-600 mt-1">
                                    {trace.filter(span =>
                                        span.attributes?.session_id === contextId ||
                                        span.attributes?.['session.id'] === contextId ||
                                        span.attributes?.sessionId === contextId ||
                                        span.attributes?.['gcp.vertex.agent.session_id'] === contextId
                                    ).length} spans with session_id = {contextId}
                                </div>
                            </div>
                            <div>
                                <strong>Time Range:</strong>
                                <div className="text-xs text-gray-600 mt-1">
                                    {new Date(Math.min(...trace.map(s => new Date(s.start_time).getTime()))).toISOString()} -
                                    {new Date(Math.max(...trace.map(s => new Date(s.end_time).getTime()))).toISOString()}
                                </div>
                            </div>
                        </div>
                    </details>
                </div>
            )}
        </div>
    );
};
