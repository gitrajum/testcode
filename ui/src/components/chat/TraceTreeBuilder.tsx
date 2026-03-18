import React from 'react';
import { TraceNode } from '@/hooks/useTrace';
import { Search, Trees, ChevronDown, ChevronRight } from 'lucide-react';

interface TraceTreeBuilderProps {
    trace: TraceNode[];
    contextId?: string;
    startFromSpan?: string;
}

interface TreeNode {
    id: string;
    name: string;
    span: TraceNode;
    children: TreeNode[];
    level: number;
    startTime: number;
    endTime: number;
    duration: number;
    isSessionSpan: boolean;
    isStartingPoint: boolean;
}

interface ProcessedTree {
    rootNode: TreeNode | null;
    allNodes: TreeNode[];
    totalSpans: number;
    maxDepth: number;
    timeline: {
        startTime: number;
        endTime: number;
        duration: number;
    };
}

export const TraceTreeBuilder: React.FC<TraceTreeBuilderProps> = ({
    trace,
    contextId,
    startFromSpan = "a2a.server.request_handlers.default_request_handler.DefaultRequestHandler._run_event_stream"
}) => {
    const [expandedNodes, setExpandedNodes] = React.useState<Set<string>>(new Set());
    const [selectedNode, setSelectedNode] = React.useState<TreeNode | null>(null);
    const [searchTerm, setSearchTerm] = React.useState(startFromSpan);
    const [isClient, setIsClient] = React.useState(false);

    React.useEffect(() => {
        setIsClient(true);
    }, []);

    // Функция для определения session span
    const isSessionSpan = React.useCallback((span: TraceNode): boolean => {
        if (!contextId) return false;

        const sessionId = span.attributes?.session_id ||
                         span.attributes?.['session.id'] ||
                         span.attributes?.sessionId ||
                         span.attributes?.['gcp.vertex.agent.session_id'];

        return sessionId === contextId;
    }, [contextId]);

    // Построение дерева трейсов
    const buildTraceTree = React.useCallback((spans: TraceNode[], startSpanName: string): ProcessedTree => {
        console.log(`Building trace tree starting from: ${startSpanName}`);
        console.log(`Total spans available: ${spans.length}`);

        // Создаем карту всех узлов
        const allNodesMap = new Map<string, TreeNode>();

        // Временная информация
        const timeStamps = spans.map(span => ({
            start: new Date(span.start_time).getTime(),
            end: new Date(span.end_time).getTime(),
            span
        })).sort((a, b) => a.start - b.start);

        const traceStartTime = timeStamps[0]?.start || 0;
        const traceEndTime = Math.max(...timeStamps.map(t => t.end));
        const traceDuration = traceEndTime - traceStartTime;

        // Создаем узлы
        spans.forEach(span => {
            const startTime = new Date(span.start_time).getTime();
            const endTime = new Date(span.end_time).getTime();
            const duration = endTime - startTime;

            const node: TreeNode = {
                id: span.id,
                name: span.name || 'Unknown',
                span,
                children: [],
                level: 0,
                startTime,
                endTime,
                duration,
                isSessionSpan: isSessionSpan(span),
                isStartingPoint: span.name === startSpanName
            };

            allNodesMap.set(span.id, node);
        });

        // Строим иерархические связи
        allNodesMap.forEach(node => {
            const parentId = node.span.parent_id;
            if (parentId && allNodesMap.has(parentId)) {
                const parent = allNodesMap.get(parentId)!;
                parent.children.push(node);
            }
        });

        // Находим стартовый узел
        let startingNode: TreeNode | null = null;

        // Сначала ищем точное совпадение по имени
        for (const node of allNodesMap.values()) {
            if (node.name === startSpanName) {
                startingNode = node;
                console.log(`Found exact match for starting span: ${node.name} (${node.id.substring(0, 8)})`);
                break;
            }
        }

        // Если точного совпадения нет, ищем частичное совпадение
        if (!startingNode) {
            for (const node of allNodesMap.values()) {
                if (node.name.includes(startSpanName) || startSpanName.includes(node.name)) {
                    startingNode = node;
                    console.log(`Found partial match for starting span: ${node.name} (${node.id.substring(0, 8)})`);
                    break;
                }
            }
        }

        // Если все еще не найден, ищем по ключевым словам
        if (!startingNode) {
            const keywords = ['_run_event_stream', 'DefaultRequestHandler', 'request_handler'];
            for (const keyword of keywords) {
                for (const node of allNodesMap.values()) {
                    if (node.name.toLowerCase().includes(keyword.toLowerCase())) {
                        startingNode = node;
                        console.log(`Found keyword match for starting span: ${node.name} (${node.id.substring(0, 8)})`);
                        break;
                    }
                }
                if (startingNode) break;
            }
        }

        // Если стартовый узел не найден, берем первый корневой узел
        if (!startingNode) {
            const rootNodes = Array.from(allNodesMap.values()).filter(node => !node.span.parent_id);
            startingNode = rootNodes[0] || null;
            console.log(`No matching span found, using first root node: ${startingNode?.name || 'none'}`);
        }

        if (!startingNode) {
            return {
                rootNode: null,
                allNodes: [],
                totalSpans: 0,
                maxDepth: 0,
                timeline: { startTime: traceStartTime, endTime: traceEndTime, duration: traceDuration }
            };
        }

        // Собираем поддерево начиная со стартового узла
        const collectSubtree = (node: TreeNode, level: number = 0, visited = new Set<string>()): TreeNode[] => {
            if (visited.has(node.id)) return [];
            visited.add(node.id);

            node.level = level;
            const subtree = [node];

            // Сортируем детей по времени начала
            const sortedChildren = [...node.children].sort((a, b) => a.startTime - b.startTime);

            sortedChildren.forEach(child => {
                subtree.push(...collectSubtree(child, level + 1, visited));
            });

            return subtree;
        };

        const treeNodes = collectSubtree(startingNode);
        const maxDepth = Math.max(...treeNodes.map(n => n.level));

        console.log(`Built tree with ${treeNodes.length} nodes, max depth: ${maxDepth}`);
        console.log(`Starting from: ${startingNode.name} at ${new Date(startingNode.startTime).toISOString()}`);

        return {
            rootNode: startingNode,
            allNodes: treeNodes,
            totalSpans: treeNodes.length,
            maxDepth,
            timeline: { startTime: traceStartTime, endTime: traceEndTime, duration: traceDuration }
        };
    }, [isSessionSpan]);

    // Обработка трейса
    const processedTree = React.useMemo(() => {
        if (!trace.length) return null;

        // Группируем по trace_id и берем первый трейс
        const traceGroups = new Map<string, TraceNode[]>();
        trace.forEach(span => {
            const traceId = span.context.trace_id;
            if (!traceGroups.has(traceId)) {
                traceGroups.set(traceId, []);
            }
            traceGroups.get(traceId)!.push(span);
        });

        const firstTrace = Array.from(traceGroups.values())[0];
        if (!firstTrace) return null;

        return buildTraceTree(firstTrace, searchTerm);
    }, [trace, searchTerm, buildTraceTree]);

    // Обработчики событий
    const toggleNode = React.useCallback((nodeId: string) => {
        setExpandedNodes(prev => {
            const newSet = new Set(prev);
            if (newSet.has(nodeId)) {
                newSet.delete(nodeId);
            } else {
                newSet.add(nodeId);
            }
            return newSet;
        });
    }, []);

    const handleNodeClick = React.useCallback((node: TreeNode) => {
        setSelectedNode(prev => prev?.id === node.id ? null : node);
    }, []);

    const handleSearchChange = React.useCallback((value: string) => {
        setSearchTerm(value);
    }, []);

    // Форматирование времени
    const formatDuration = React.useCallback((duration: number) => {
        if (duration < 1000) return `${duration}ms`;
        if (duration < 60000) return `${(duration / 1000).toFixed(2)}s`;
        return `${(duration / 60000).toFixed(2)}m`;
    }, []);

    const formatTimestamp = React.useCallback((timestamp: number) => {
        const date = new Date(timestamp);
        return date.toLocaleTimeString('ru-RU', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });
    }, []);

    // Рендер узла дерева
    const renderTreeNode = React.useCallback((node: TreeNode) => {
        const hasChildren = node.children.length > 0;
        const isExpanded = expandedNodes.has(node.id);
        const isSelected = selectedNode?.id === node.id;
        const indent = node.level * 24;

        return (
            <div key={node.id} className="select-none">
                <div
                    className={`flex items-center py-2 px-3 cursor-pointer hover:bg-gray-50 ${
                        isSelected ? 'bg-blue-50 border-l-4 border-blue-500' : ''
                    } ${node.isStartingPoint ? 'bg-yellow-50 border-l-4 border-yellow-500' : ''}`}
                    style={{ paddingLeft: `${12 + indent}px` }}
                    onClick={() => handleNodeClick(node)}
                >
                    {/* Expand/Collapse button */}
                    <div className="w-6 h-6 flex items-center justify-center mr-2">
                        {hasChildren ? (
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    toggleNode(node.id);
                                }}
                                className="p-1 hover:bg-gray-200 rounded"
                            >
                                {isExpanded ? (
                                    <ChevronDown className="h-4 w-4 text-gray-600" />
                                ) : (
                                    <ChevronRight className="h-4 w-4 text-gray-600" />
                                )}
                            </button>
                        ) : (
                            <div className="w-4 h-4" />
                        )}
                    </div>

                    {/* Node icon */}
                    <div className="w-6 h-6 flex items-center justify-center mr-3">
                        {node.isStartingPoint ? (
                            <div className="w-3 h-3 bg-yellow-500 rounded-full" />
                        ) : node.isSessionSpan ? (
                            <div className="w-3 h-3 bg-blue-500 rounded-full" />
                        ) : (
                            <div className="w-3 h-3 bg-gray-400 rounded-full" />
                        )}
                    </div>

                    {/* Node content */}
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium text-gray-900 truncate">
                                    {node.name}
                                    {node.isStartingPoint && (
                                        <span className="ml-2 px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded">
                                            START
                                        </span>
                                    )}
                                    {node.isSessionSpan && (
                                        <span className="ml-2 px-2 py-1 text-xs bg-blue-100 text-blue-800 rounded">
                                            SESSION
                                        </span>
                                    )}
                                </div>
                                <div className="text-xs text-gray-500 mt-1">
                                    {formatTimestamp(node.startTime)} • {formatDuration(node.duration)} • {node.span.status_code}
                                </div>
                            </div>
                            {hasChildren && (
                                <div className="text-xs text-gray-400 ml-2">
                                    {node.children.length} child{node.children.length !== 1 ? 'ren' : ''}
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Children */}
                {hasChildren && isExpanded && (
                    <div>
                        {node.children
                            .sort((a, b) => a.startTime - b.startTime)
                            .map(child => renderTreeNode(child))
                        }
                    </div>
                )}
            </div>
        );
    }, [expandedNodes, selectedNode, toggleNode, handleNodeClick, formatDuration, formatTimestamp]);

    if (!isClient) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-500">
                Loading trace tree builder...
            </div>
        );
    }

    if (!processedTree || !processedTree.rootNode) {
        return (
            <div className="flex flex-col items-center justify-center h-64 text-gray-500">
                <Trees className="h-12 w-12 mb-4 text-gray-300" />
                <div className="text-center">
                    <div className="font-medium">No trace tree available</div>
                    <div className="text-sm mt-1">
                        Could not find span: "{searchTerm}"
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className="w-full h-full flex flex-col bg-white">
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 flex-shrink-0">
                <div className="flex items-center gap-4">
                    <Trees className="h-6 w-6 text-blue-600" />
                    <div>
                        <h2 className="text-lg font-semibold text-gray-900">Trace Tree</h2>
                        <div className="text-sm text-gray-600">
                            {processedTree.totalSpans} spans • Max depth: {processedTree.maxDepth}
                        </div>
                    </div>
                </div>

                {/* Search */}
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
                        <input
                            type="text"
                            value={searchTerm}
                            onChange={(e) => handleSearchChange(e.target.value)}
                            placeholder="Search for starting span..."
                            className="pl-10 pr-4 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                        />
                    </div>
                </div>
            </div>

            {/* Timeline info */}
            <div className="bg-gray-50 border-b border-gray-200 p-3 flex-shrink-0">
                <div className="flex items-center justify-between text-sm text-gray-600">
                    <span>Start: {formatTimestamp(processedTree.timeline.startTime)}</span>
                    <span>Duration: {formatDuration(processedTree.timeline.duration)}</span>
                    <span>End: {formatTimestamp(processedTree.timeline.endTime)}</span>
                </div>
            </div>

            {/* Tree content */}
            <div className="flex-1 flex min-h-0">
                {/* Tree view */}
                <div className={`${selectedNode ? 'w-1/2' : 'w-full'} border-r border-gray-200 overflow-auto`}>
                    <div className="p-2">
                        {renderTreeNode(processedTree.rootNode)}
                    </div>
                </div>

                {/* Details panel */}
                {selectedNode && (
                    <div className="w-1/2 overflow-auto">
                        <div className="p-4">
                            <div className="flex items-center justify-between mb-4">
                                <h3 className="text-lg font-semibold text-gray-800">
                                    Span Details
                                </h3>
                                <button
                                    onClick={() => setSelectedNode(null)}
                                    className="text-gray-500 hover:text-gray-700"
                                >
                                    ✕
                                </button>
                            </div>

                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-1">
                                        Name
                                    </label>
                                    <div className="text-sm text-gray-800 font-mono bg-gray-50 p-2 rounded">
                                        {selectedNode.name}
                                    </div>
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-1">
                                            Level
                                        </label>
                                        <div className="text-sm text-gray-800">
                                            {selectedNode.level}
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-1">
                                            Children
                                        </label>
                                        <div className="text-sm text-gray-800">
                                            {selectedNode.children.length}
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-1">
                                            Start Time
                                        </label>
                                        <div className="text-sm text-gray-800">
                                            {formatTimestamp(selectedNode.startTime)}
                                        </div>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-1">
                                            Duration
                                        </label>
                                        <div className="text-sm text-gray-800">
                                            {formatDuration(selectedNode.duration)}
                                        </div>
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-600 mb-1">
                                        Status
                                    </label>
                                    <div className={`inline-block px-2 py-1 rounded text-sm font-medium ${
                                        selectedNode.span.status_code === 'OK'
                                            ? 'bg-green-100 text-green-800'
                                            : selectedNode.span.status_code === 'ERROR'
                                            ? 'bg-red-100 text-red-800'
                                            : 'bg-gray-100 text-gray-800'
                                    }`}>
                                        {selectedNode.span.status_code}
                                        {selectedNode.isSessionSpan && ' • SESSION'}
                                        {selectedNode.isStartingPoint && ' • START POINT'}
                                    </div>
                                </div>

                                {/* Attributes */}
                                {selectedNode.span.attributes && Object.keys(selectedNode.span.attributes).length > 0 && (
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-2">
                                            Attributes
                                        </label>
                                        <div className="bg-gray-50 rounded-lg p-3 max-h-40 overflow-auto">
                                            <pre className="text-xs text-gray-700">
                                                {JSON.stringify(selectedNode.span.attributes, null, 2)}
                                            </pre>
                                        </div>
                                    </div>
                                )}

                                {/* Events */}
                                {selectedNode.span.events && selectedNode.span.events.length > 0 && (
                                    <div>
                                        <label className="block text-sm font-medium text-gray-600 mb-2">
                                            Events ({selectedNode.span.events.length})
                                        </label>
                                        <div className="space-y-2 max-h-40 overflow-auto">
                                            {selectedNode.span.events.map((event, index) => (
                                                <div key={index} className="bg-gray-50 rounded-lg p-3">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <span className="text-sm font-medium text-gray-800">
                                                            {event.name}
                                                        </span>
                                                        <span className="text-xs text-gray-500">
                                                            {formatTimestamp(new Date(event.timestamp).getTime())}
                                                        </span>
                                                    </div>
                                                    {event.attributes && (
                                                        <pre className="text-xs text-gray-600 mt-1">
                                                            {JSON.stringify(event.attributes, null, 2)}
                                                        </pre>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
