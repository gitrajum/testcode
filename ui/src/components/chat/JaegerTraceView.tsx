import React, { useState, useMemo } from 'react';
import { TraceNode } from '@/hooks/useTrace';
import {
    ChevronDown,
    ChevronRight,
    ChevronLeft,
    ChevronRight as ChevronRightNav,
    Clock,
    Zap,
    AlertCircle,
    Expand,
    Minimize2,
    Search,
    Filter,
    Eye,
    EyeOff,
    Activity,
    Database,
    Cpu,
    Globe,
    Settings,
    BarChart3,
    Timer,
    CheckCircle,
    XCircle,
    AlertTriangle,
    ExternalLink,
    Hash,
    ToggleLeft,
    Braces,
    Type
} from 'lucide-react';

interface JaegerTraceViewProps {
    trace: TraceNode[];
    contextId?: string;
}

interface ProcessedSpan {
    id: string;
    name: string;
    operationName: string;
    serviceName: string;
    startTime: number;
    endTime: number;
    duration: number;
    depth: number;
    hasChildren: boolean;
    children: ProcessedSpan[];
    parent?: ProcessedSpan;
    span: TraceNode;
    isSessionSpan: boolean;
    relativeStart: number;
    relativeEnd: number;
    color: string;
}

interface TraceTimeline {
    spans: ProcessedSpan[];
    totalDuration: number;
    startTime: number;
    endTime: number;
    maxDepth: number;
    traceId: string;
}

interface TraceGroup {
    traceId: string;
    spans: TraceNode[];
    sessionSpansCount: number;
    startTime: number;
    endTime: number;
    duration: number;
}

export const JaegerTraceView: React.FC<JaegerTraceViewProps> = ({ trace, contextId }) => {
    // Состояние для выбранного трейса
    const [selectedTraceIndex, setSelectedTraceIndex] = useState(0);

    // Группируем трейсы и выбираем активный
    const traceGroups = useMemo(() => {
        const groups = new Map<string, TraceNode[]>();
        trace.forEach(span => {
            const traceId = span.context.trace_id;
            if (!groups.has(traceId)) {
                groups.set(traceId, []);
            }
            groups.get(traceId)!.push(span);
        });

        return Array.from(groups.entries())
            .map(([traceId, spans]) => {
                const timeStamps = spans.map(span => ({
                    start: new Date(span.start_time).getTime(),
                    end: new Date(span.end_time).getTime()
                }));

                const startTime = Math.min(...timeStamps.map(t => t.start));
                const endTime = Math.max(...timeStamps.map(t => t.end));
                const duration = endTime - startTime;

                const sessionSpansCount = spans.filter(span =>
                    contextId && (
                        span.attributes?.session_id === contextId ||
                        span.attributes?.['session.id'] === contextId ||
                        span.attributes?.sessionId === contextId ||
                        span.attributes?.['gcp.vertex.agent.session_id'] === contextId
                    )
                ).length;

                return {
                    traceId,
                    spans,
                    sessionSpansCount,
                    startTime,
                    endTime,
                    duration
                } as TraceGroup;
            })
            .filter(group => {
                // Показываем только трейсы, которые содержат session spans (если contextId указан)
                return !contextId || group.sessionSpansCount > 0;
            })
            .sort((a, b) => a.startTime - b.startTime); // Сортируем по времени начала
    }, [trace, contextId]);

    // Автоматически выбираем последний трейс при обновлении данных
    React.useEffect(() => {
        if (traceGroups.length > 0) {
            const latestTraceIndex = traceGroups.length - 1;
            console.log(`JaegerTraceView: Auto-selecting latest trace (index ${latestTraceIndex} of ${traceGroups.length})`);
            setSelectedTraceIndex(latestTraceIndex);
        }
    }, [traceGroups]);

    const currentTraceGroup = traceGroups[selectedTraceIndex];
    const currentTrace = currentTraceGroup?.spans || [];

    // Состояния для UI
    const [expandedSpans, setExpandedSpans] = useState<Set<string>>(() => {
        return new Set(currentTrace.map(span => span.id));
    });
    const [selectedSpan, setSelectedSpan] = useState<ProcessedSpan | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [showFilters, setShowFilters] = useState(false);
    const [statusFilter, setStatusFilter] = useState<string>('all');
    const [serviceFilter, setServiceFilter] = useState<string>('all');
    const [durationFilter, setDurationFilter] = useState<string>('all');
    const [showOnlyErrors, setShowOnlyErrors] = useState(false);
    const [showOnlySession, setShowOnlySession] = useState(false);

    // Обновляем expandedSpans когда меняется текущий трейс
    React.useEffect(() => {
        const allSpanIds = new Set(currentTrace.map(span => span.id));
        console.log(`JaegerTraceView: Setting expandedSpans with ${allSpanIds.size} span IDs`);
        setExpandedSpans(allSpanIds);
        setSelectedSpan(null);
        setSearchQuery('');
    }, [currentTrace]);

    // Цвета для разных сервисов (современная палитра)
    const serviceColors = [
        '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
        '#EC4899', '#06B6D4', '#84CC16', '#F97316', '#6366F1'
    ];

    const getServiceColor = (serviceName: string): string => {
        const hash = serviceName.split('').reduce((a, b) => {
            a = ((a << 5) - a) + b.charCodeAt(0);
            return a & a;
        }, 0);
        return serviceColors[Math.abs(hash) % serviceColors.length];
    };

    const extractServiceName = (spanName: string): string => {
        const parts = spanName.split('.');
        if (parts.length >= 2) {
            return parts.slice(0, 2).join('.');
        }
        return parts[0] || 'unknown';
    };

    const getStatusIcon = (statusCode: string) => {
        switch (statusCode) {
            case 'OK':
                return <CheckCircle className="h-4 w-4 text-green-500" />;
            case 'ERROR':
                return <XCircle className="h-4 w-4 text-red-500" />;
            default:
                return <AlertTriangle className="h-4 w-4 text-yellow-500" />;
        }
    };

    const getServiceIcon = (serviceName: string) => {
        if (serviceName.includes('llm')) return <Cpu className="h-4 w-4" />;
        if (serviceName.includes('agent')) return <Activity className="h-4 w-4" />;
        if (serviceName.includes('database')) return <Database className="h-4 w-4" />;
        if (serviceName.includes('api')) return <Globe className="h-4 w-4" />;
        return <Settings className="h-4 w-4" />;
    };

    const processTrace = useMemo((): TraceTimeline | null => {
        if (!currentTrace.length) return null;

        // Ищем стартовый спан DefaultRequestHandler._run_event_stream
        const startSpanName = 'a2a.server.request_handlers.default_request_handler.DefaultRequestHandler._run_event_stream';
        const startSpan = currentTrace.find(span => span.name === startSpanName);

        if (!startSpan) {
            console.log(`JaegerTraceView: Start span "${startSpanName}" not found in trace`);
        } else {
            console.log(`JaegerTraceView: Found start span "${startSpanName}" (${startSpan.id})`);
        }

        // Создаем карту спанов
        const spanMap = new Map<string, ProcessedSpan>();
        const timeStamps = currentTrace.map(span => ({
            start: new Date(span.start_time).getTime(),
            end: new Date(span.end_time).getTime()
        }));

        const traceStartTime = Math.min(...timeStamps.map(t => t.start));
        const traceEndTime = Math.max(...timeStamps.map(t => t.end));
        const totalDuration = traceEndTime - traceStartTime;

        // Создаем ProcessedSpan для каждого span
        currentTrace.forEach(span => {
            const startTime = new Date(span.start_time).getTime();
            const endTime = new Date(span.end_time).getTime();
            const duration = endTime - startTime;
            const serviceName = extractServiceName(span.name);

            const isSessionSpan = contextId && (
                span.attributes?.session_id === contextId ||
                span.attributes?.['session.id'] === contextId ||
                span.attributes?.sessionId === contextId ||
                span.attributes?.['gcp.vertex.agent.session_id'] === contextId
            );

            const processedSpan: ProcessedSpan = {
                id: span.id,
                name: span.name,
                operationName: span.name.split('.').pop() || span.name,
                serviceName,
                startTime,
                endTime,
                duration,
                depth: 0,
                hasChildren: false,
                children: [],
                span,
                isSessionSpan: !!isSessionSpan,
                relativeStart: ((startTime - traceStartTime) / totalDuration) * 100,
                relativeEnd: ((endTime - traceStartTime) / totalDuration) * 100,
                color: getServiceColor(serviceName)
            };

            spanMap.set(span.id, processedSpan);
        });

        // Строим иерархию
        const rootSpans: ProcessedSpan[] = [];

        console.log('JaegerTraceView: All span IDs and parent_ids:');
        currentTrace.forEach(span => {
            console.log(`  ${span.name}: id=${span.id}, context.span_id=${span.context.span_id}, parent_id=${span.parent_id}`);
        });

        spanMap.forEach(span => {
            const parentId = span.span.parent_id;
            if (parentId) {
                let parent = spanMap.get(parentId);
                if (!parent) {
                    for (const [_, candidateSpan] of spanMap) {
                        if (candidateSpan.span.context.span_id === parentId) {
                            parent = candidateSpan;
                            break;
                        }
                    }
                }

                if (parent) {
                    parent.children.push(span);
                    parent.hasChildren = true;
                    span.parent = parent;
                    console.log(`JaegerTraceView: Linked ${span.name} to parent ${parent.name}`);
                } else {
                    console.log(`JaegerTraceView: Parent not found for ${span.name} (parent_id: ${parentId})`);
                    rootSpans.push(span);
                }
            } else {
                rootSpans.push(span);
            }
        });

        console.log(`JaegerTraceView: Built hierarchy - ${rootSpans.length} root spans`);
        rootSpans.forEach(root => {
            console.log(`  Root: ${root.name} (${root.children.length} children)`);
        });

        // Если найден стартовый спан, используем его как единственный корень
        let finalRootSpans = rootSpans;
        if (startSpan) {
            const startProcessedSpan = spanMap.get(startSpan.id);
            if (startProcessedSpan) {
                finalRootSpans = [startProcessedSpan];
                console.log(`JaegerTraceView: Using start span as single root, showing only its subtree`);
                console.log(`JaegerTraceView: Start span has ${startProcessedSpan.children.length} direct children`);

                const logSpanTree = (span: ProcessedSpan, indent = '') => {
                    console.log(`${indent}${span.name} (${span.id}) - children: ${span.children.length}`);
                    span.children.forEach(child => logSpanTree(child, indent + '  '));
                };
                logSpanTree(startProcessedSpan);
            }
        }

        // Вычисляем глубину
        const calculateDepth = (spans: ProcessedSpan[], depth = 0) => {
            spans.forEach(span => {
                span.depth = depth;
                if (span.children.length > 0) {
                    span.children.sort((a, b) => a.startTime - b.startTime);
                    calculateDepth(span.children, depth + 1);
                }
            });
        };

        finalRootSpans.sort((a, b) => a.startTime - b.startTime);
        calculateDepth(finalRootSpans);

        // Собираем все спаны в плоский список для отображения
        const flattenSpans = (spans: ProcessedSpan[]): ProcessedSpan[] => {
            const result: ProcessedSpan[] = [];
            spans.forEach(span => {
                result.push(span);
                const isExpanded = expandedSpans.has(span.id);
                const hasChildren = span.children.length > 0;

                if (span.name.includes('DefaultRequestHandler')) {
                    console.log(`JaegerTraceView: Processing ${span.name} - expanded: ${isExpanded}, children: ${hasChildren} (${span.children.length})`);
                }

                if (isExpanded && hasChildren) {
                    const childResults = flattenSpans(span.children);
                    result.push(...childResults);

                    if (span.name.includes('DefaultRequestHandler')) {
                        console.log(`JaegerTraceView: Added ${childResults.length} children for ${span.name}`);
                    }
                }
            });
            return result;
        };

        const allSpans = flattenSpans(finalRootSpans);
        const maxDepth = Math.max(...Array.from(spanMap.values()).map(s => s.depth));

        console.log(`JaegerTraceView: Final result - ${allSpans.length} spans for display`);
        console.log(`JaegerTraceView: Spans:`, allSpans.map(s => ({ name: s.name, depth: s.depth, hasChildren: s.hasChildren })));

        // Фильтруем спаны - исключаем те, которые содержат "a2a.server" в названии
        const filteredSpans = allSpans.filter(span => !span.name.includes('a2a.server'));
        console.log(`JaegerTraceView: After filtering out a2a.server spans: ${filteredSpans.length} spans (was ${allSpans.length})`);

        // Пересчитываем глубину для отфильтрованных спанов
        const recalculateDepth = (spans: ProcessedSpan[]) => {
            const minDepth = Math.min(...spans.map(s => s.depth));
            spans.forEach(span => {
                span.depth = span.depth - minDepth;
            });
        };

        if (filteredSpans.length > 0) {
            recalculateDepth(filteredSpans);
        }

        return {
            spans: filteredSpans,
            totalDuration,
            startTime: traceStartTime,
            endTime: traceEndTime,
            maxDepth: filteredSpans.length > 0 ? Math.max(...filteredSpans.map(s => s.depth)) : 0,
            traceId: currentTraceGroup.traceId
        };
    }, [currentTrace, contextId, expandedSpans]);

    // Фильтрация спанов
    const filteredSpans = useMemo(() => {
        if (!processTrace) return [];

        let spans = processTrace.spans;

        // Поиск
        if (searchQuery) {
            spans = spans.filter(span =>
                span.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                span.operationName.toLowerCase().includes(searchQuery.toLowerCase()) ||
                span.serviceName.toLowerCase().includes(searchQuery.toLowerCase())
            );
        }

        // Фильтр по статусу
        if (statusFilter !== 'all') {
            spans = spans.filter(span => span.span.status_code === statusFilter);
        }

        // Фильтр по сервису
        if (serviceFilter !== 'all') {
            spans = spans.filter(span => span.serviceName === serviceFilter);
        }

        // Фильтр по длительности
        if (durationFilter !== 'all') {
            spans = spans.filter(span => {
                const duration = span.duration;
                switch (durationFilter) {
                    case 'fast': return duration < 100;
                    case 'medium': return duration >= 100 && duration < 1000;
                    case 'slow': return duration >= 1000;
                    default: return true;
                }
            });
        }

        // Только ошибки
        if (showOnlyErrors) {
            spans = spans.filter(span => span.span.status_code === 'ERROR');
        }

        // Только session спаны
        if (showOnlySession) {
            spans = spans.filter(span => span.isSessionSpan);
        }

        return spans;
    }, [processTrace, searchQuery, statusFilter, serviceFilter, durationFilter, showOnlyErrors, showOnlySession]);

    // Получаем уникальные сервисы для фильтра
    const uniqueServices = useMemo(() => {
        if (!processTrace) return [];
        return Array.from(new Set(processTrace.spans.map(span => span.serviceName))).sort();
    }, [processTrace]);

    const toggleSpan = (spanId: string) => {
        setExpandedSpans(prev => {
            const newSet = new Set(prev);
            if (newSet.has(spanId)) {
                newSet.delete(spanId);
            } else {
                newSet.add(spanId);
            }
            return newSet;
        });
    };

    const expandAll = () => {
        setExpandedSpans(new Set(currentTrace.map(span => span.id)));
    };

    const collapseAll = () => {
        setExpandedSpans(new Set());
    };

    const goToPreviousTrace = () => {
        if (selectedTraceIndex > 0) {
            setSelectedTraceIndex(selectedTraceIndex - 1);
        }
    };

    const goToNextTrace = () => {
        if (selectedTraceIndex < traceGroups.length - 1) {
            setSelectedTraceIndex(selectedTraceIndex + 1);
        }
    };

    const formatDuration = (duration: number): string => {
        if (duration < 1000) return `${duration.toFixed(1)}ms`;
        if (duration < 60000) return `${(duration / 1000).toFixed(2)}s`;
        return `${(duration / 60000).toFixed(2)}m`;
    };

    const formatTime = (timestamp: number): string => {
        return new Date(timestamp).toLocaleTimeString('ru-RU', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });
    };

    if (!processTrace) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-500">
                <div className="text-center">
                    <AlertCircle className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                    <div className="font-medium">No trace data available</div>
                </div>
            </div>
        );
    }

    const { spans, totalDuration, startTime, endTime } = processTrace;

    return (
        <div className="w-full h-full flex flex-col bg-gradient-to-br from-gray-50 to-gray-100">
            {/* Максимально компактный заголовок */}
            <div className="bg-white border-b border-gray-200 shadow-sm flex-shrink-0">
                {/* Основная информация - одна строка */}
                <div className="flex items-center justify-between p-2">
                    <div className="flex items-center gap-1.5">
                        <div className="p-1 bg-blue-100 rounded">
                            <BarChart3 className="h-3 w-3 text-blue-600" />
                        </div>
                        <div>
                            <h2 className="text-sm font-bold text-gray-900 leading-tight">Trace Timeline</h2>
                            <p className="text-xs text-gray-500 leading-tight">Jaeger visualization</p>
                        </div>
                    </div>

                    {/* Компактная статистика */}
                    <div className="flex items-center gap-1.5 text-xs">
                        <div className="flex items-center gap-1 px-1.5 py-0.5 bg-blue-50 rounded">
                            <Zap className="h-3 w-3 text-blue-600" />
                            <span className="font-medium text-blue-900">{filteredSpans.length}</span>
                        </div>
                        <div className="flex items-center gap-1 px-1.5 py-0.5 bg-green-50 rounded">
                            <Clock className="h-3 w-3 text-green-600" />
                            <span className="font-medium text-green-900">{formatDuration(totalDuration)}</span>
                        </div>
                        {contextId && (
                            <div className="px-1.5 py-0.5 bg-purple-50 text-purple-900 rounded text-xs font-medium">
                                Session
                            </div>
                        )}
                    </div>
                </div>

                {/* Навигация по трейсам - компактная */}
                {traceGroups.length > 1 && (
                    <div className="flex items-center justify-center px-2 pb-1">
                        <div className="flex items-center gap-1 px-2 py-1 bg-gray-50 rounded border text-xs">
                            <button
                                onClick={goToPreviousTrace}
                                disabled={selectedTraceIndex === 0}
                                className="p-0.5 hover:bg-white rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                title="Previous trace"
                            >
                                <ChevronLeft className="h-3 w-3" />
                            </button>

                            <span className="font-semibold text-gray-900 px-1">
                                {selectedTraceIndex + 1}/{traceGroups.length}
                            </span>

                            <button
                                onClick={goToNextTrace}
                                disabled={selectedTraceIndex === traceGroups.length - 1}
                                className="p-0.5 hover:bg-white rounded disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                                title="Next trace"
                            >
                                <ChevronRightNav className="h-3 w-3" />
                            </button>
                        </div>
                    </div>
                )}

                {/* Максимально компактный поиск и фильтры */}
                <div className="px-2 pb-2">
                    <div className="flex items-center gap-1.5">
                        {/* Поиск */}
                        <div className="flex-1 relative">
                            <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-gray-400" />
                            <input
                                type="text"
                                placeholder="Search spans..."
                                value={searchQuery}
                                onChange={(e) => setSearchQuery(e.target.value)}
                                className="w-full pl-7 pr-2 py-1 text-xs border border-gray-200 rounded focus:ring-1 focus:ring-blue-500 focus:border-transparent"
                            />
                        </div>

                        {/* Кнопки управления */}
                        <button
                            onClick={() => setShowFilters(!showFilters)}
                            className={`flex items-center gap-1 px-1.5 py-1 rounded text-xs border transition-colors ${
                                showFilters
                                    ? 'bg-blue-50 border-blue-200 text-blue-700'
                                    : 'bg-white border-gray-200 text-gray-700 hover:bg-gray-50'
                            }`}
                        >
                            <Filter className="h-3 w-3" />
                            Filters
                        </button>

                        <button
                            onClick={expandAll}
                            className="flex items-center gap-1 px-1.5 py-1 text-xs bg-blue-50 hover:bg-blue-100 text-blue-700 rounded transition-colors"
                            title="Expand all"
                        >
                            <Expand className="h-3 w-3" />
                            All
                        </button>
                    </div>

                    {/* Максимально компактные фильтры */}
                    {showFilters && (
                        <div className="grid grid-cols-3 gap-1.5 p-2 bg-gray-50 rounded border text-xs mt-1">
                            <select
                                value={statusFilter}
                                onChange={(e) => setStatusFilter(e.target.value)}
                                className="px-1.5 py-1 border border-gray-200 rounded text-xs"
                            >
                                <option value="all">All Status</option>
                                <option value="OK">OK</option>
                                <option value="ERROR">Error</option>
                            </select>

                            <select
                                value={serviceFilter}
                                onChange={(e) => setServiceFilter(e.target.value)}
                                className="px-1.5 py-1 border border-gray-200 rounded text-xs"
                            >
                                <option value="all">All Services</option>
                                {uniqueServices.map(service => (
                                    <option key={service} value={service}>{service}</option>
                                ))}
                            </select>

                            <label className="flex items-center gap-1">
                                <input
                                    type="checkbox"
                                    checked={showOnlyErrors}
                                    onChange={(e) => setShowOnlyErrors(e.target.checked)}
                                    className="rounded border-gray-300"
                                />
                                <span>Errors only</span>
                            </label>
                        </div>
                    )}
                </div>
            </div>

            {/* Основной контент - flex для разделения timeline и детальной панели */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Timeline - уменьшается когда выбран span */}
                <div className={`${selectedSpan ? 'h-1/3' : 'flex-1'} overflow-auto bg-white border-b border-gray-200`}>
                    <div className="min-w-full">
                        {/* Компактный заголовок таблицы */}
                        <div className="sticky top-0 bg-white border-b border-gray-200 z-10 shadow-sm">
                            <div className="flex text-xs">
                                {/* Колонка сервиса - адаптивная ширина */}
                                <div className="w-48 sm:w-64 md:w-80 p-2 border-r border-gray-200 bg-gradient-to-r from-gray-50 to-white">
                                    <div className="font-semibold text-gray-900 flex items-center gap-1">
                                        <Activity className="h-3 w-3" />
                                        Service & Operation
                                    </div>
                                    <div className="text-xs text-gray-500 mt-0.5">
                                        {formatTime(startTime)} - {formatTime(endTime)}
                                    </div>
                                </div>

                                {/* Колонка таймлайна */}
                                <div className="flex-1 p-2 bg-gradient-to-r from-white to-gray-50">
                                    <div className="font-semibold text-gray-900 flex items-center gap-1">
                                        <Timer className="h-3 w-3" />
                                        Timeline ({formatDuration(totalDuration)})
                                    </div>
                                    <div className="text-xs text-gray-500 mt-0.5">
                                        {filteredSpans.length} of {spans.length} spans
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Компактные спаны */}
                        <div className="divide-y divide-gray-100">
                            {filteredSpans.map((span, index) => (
                                <div
                                    key={span.id}
                                    className={`flex hover:bg-blue-50 transition-colors ${
                                        selectedSpan?.id === span.id ? 'bg-blue-100 border-l-2 border-blue-500' : ''
                                    } ${span.isSessionSpan ? 'bg-purple-50' : ''}`}
                                >
                                    {/* Компактная колонка сервиса */}
                                    <div className="w-48 sm:w-64 md:w-80 p-2 border-r border-gray-200">
                                        <div className="flex items-center gap-1" style={{ paddingLeft: `${Math.min(span.depth * 12, 48)}px` }}>
                                            {/* Кнопка expand/collapse */}
                                            {span.hasChildren && (
                                                <button
                                                    onClick={() => toggleSpan(span.id)}
                                                    className="p-0.5 hover:bg-gray-200 rounded transition-colors"
                                                >
                                                    {expandedSpans.has(span.id) ? (
                                                        <ChevronDown className="h-3 w-3 text-gray-600" />
                                                    ) : (
                                                        <ChevronRight className="h-3 w-3 text-gray-600" />
                                                    )}
                                                </button>
                                            )}

                                            {/* Компактная иконка сервиса */}
                                            <div className="p-1 rounded" style={{ backgroundColor: span.color + '20' }}>
                                                {React.cloneElement(getServiceIcon(span.serviceName), { className: "h-3 w-3" })}
                                            </div>

                                            {/* Информация о спане */}
                                            <div className="flex-1 min-w-0">
                                                <div className="flex items-center gap-1">
                                                    <span className="font-medium text-gray-900 truncate text-sm">
                                                        {span.operationName}
                                                    </span>
                                                    {span.isSessionSpan && (
                                                        <span className="px-1 py-0.5 text-xs bg-purple-100 text-purple-800 rounded">
                                                            S
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-1 mt-0.5">
                                                    <span
                                                        className="text-xs px-1.5 py-0.5 rounded text-white font-medium"
                                                        style={{ backgroundColor: span.color }}
                                                    >
                                                        {span.serviceName.split('.')[0]}
                                                    </span>
                                                    <span className="text-xs text-gray-500">
                                                        {formatDuration(span.duration)}
                                                    </span>
                                                    {React.cloneElement(getStatusIcon(span.span.status_code), { className: "h-3 w-3" })}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Компактная колонка таймлайна */}
                                    <div className="flex-1 p-2 relative">
                                        <div className="relative h-6 flex items-center">
                                            {/* Компактная полоса таймлайна */}
                                            <div
                                                className="absolute h-4 rounded shadow-sm border border-gray-200 flex items-center justify-center cursor-pointer hover:shadow-md transition-shadow"
                                                style={{
                                                    left: `${span.relativeStart}%`,
                                                    width: `${Math.max(span.relativeEnd - span.relativeStart, 1)}%`,
                                                    backgroundColor: span.color,
                                                    opacity: span.span.status_code === 'ERROR' ? 0.8 : 0.7
                                                }}
                                                onClick={() => setSelectedSpan(selectedSpan?.id === span.id ? null : span)}
                                            >
                                                <span className="text-xs text-white font-medium truncate px-1">
                                                    {formatDuration(span.duration)}
                                                </span>
                                                {span.span.status_code === 'ERROR' && (
                                                    <XCircle className="h-2 w-2 text-white ml-1" />
                                                )}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Детальная панель - занимает 2/3 высоты когда выбран span */}
                {selectedSpan && (
                    <div className="h-2/3 bg-white overflow-auto">
                        <div className="p-4 h-full">
                            <div className="flex items-center justify-between mb-1 py-1">
                                <div className="flex items-center gap-1">
                                    <div className="p-0.5 rounded" style={{ backgroundColor: selectedSpan.color + '20' }}>
                                        {React.cloneElement(getServiceIcon(selectedSpan.serviceName), { className: "h-3 w-3" })}
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-semibold text-gray-900 leading-tight">
                                            {selectedSpan.operationName}
                                        </h3>
                                        <p className="text-xs text-gray-600 leading-tight">{selectedSpan.serviceName}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setSelectedSpan(null)}
                                    className="p-0.5 hover:bg-gray-100 rounded transition-colors"
                                >
                                    <XCircle className="h-3 w-3 text-gray-500" />
                                </button>
                            </div>

                            <div className="flex flex-col h-full gap-2">
                                {/* Максимально сжатая информация о span */}
                                <div className="flex-shrink-0">
                                    {/* Основная информация - максимально плоская */}
                                    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded border border-blue-200 p-2 mb-1">
                                        <div className="grid grid-cols-4 gap-2">
                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    <Clock className="h-3 w-3 text-blue-600 mr-1" />
                                                    <div className="text-xs text-gray-600">Start</div>
                                                </div>
                                                <div className="text-xs font-mono font-semibold text-gray-900 mt-0.5">
                                                    {formatTime(selectedSpan.startTime).split(' ')[1]}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    <Timer className="h-3 w-3 text-green-600 mr-1" />
                                                    <div className="text-xs text-gray-600">Duration</div>
                                                </div>
                                                <div className="text-sm font-mono font-bold text-green-700 mt-0.5">
                                                    {formatDuration(selectedSpan.duration)}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    {React.cloneElement(getStatusIcon(selectedSpan.span.status_code), { className: "h-3 w-3 mr-1" })}
                                                    <div className="text-xs text-gray-600">Status</div>
                                                </div>
                                                <div className={`text-xs font-semibold mt-0.5 ${
                                                    selectedSpan.span.status_code === 'OK' ? 'text-green-700' :
                                                    selectedSpan.span.status_code === 'ERROR' ? 'text-red-700' : 'text-yellow-700'
                                                }`}>
                                                    {selectedSpan.span.status_code}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    {React.cloneElement(getServiceIcon(selectedSpan.serviceName), { className: "h-3 w-3 mr-1" })}
                                                    <div className="text-xs text-gray-600">Service</div>
                                                </div>
                                                <div className="text-xs font-semibold truncate mt-0.5" style={{ color: selectedSpan.color }}>
                                                    {selectedSpan.serviceName.split('.')[0]}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Дополнительная информация - одна плоская строка */}
                                    <div className="flex gap-2 text-xs text-gray-600 bg-gray-50 rounded p-1.5">
                                        <span className="flex items-center gap-1">
                                            <Activity className="h-3 w-3" />
                                            <span className="font-medium">Op:</span>
                                            <span className="font-mono truncate max-w-20">{selectedSpan.operationName}</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <Settings className="h-3 w-3" />
                                            <span className="font-medium">ID:</span>
                                            <span className="font-mono truncate max-w-12">{selectedSpan.span.id}</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <Globe className="h-3 w-3" />
                                            <span className="font-medium">L{selectedSpan.depth}</span>
                                        </span>
                                        {selectedSpan.isSessionSpan && (
                                            <span className="px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">
                                                Session
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Атрибуты - занимают весь доступный контент по высоте */}
                                <div className="flex-1 flex flex-col min-h-0">
                                    {selectedSpan.span.attributes && Object.keys(selectedSpan.span.attributes).length > 0 ? (
                                        <div className="flex-1 flex flex-col min-h-0">
                                            <div className="flex-shrink-0 mb-0.5">
                                                <label className="block text-xs font-bold text-gray-900 flex items-center gap-1">
                                                    <Settings className="h-3 w-3 text-blue-600" />
                                                    Span Attributes
                                                    <span className="px-1 py-0.5 text-xs bg-blue-100 text-blue-700 rounded font-medium">
                                                        {Object.keys(selectedSpan.span.attributes).length}
                                                    </span>
                                                </label>
                                            </div>

                                            <div className="flex-1 bg-gradient-to-br from-gray-50 to-gray-100 rounded border border-gray-200 overflow-hidden min-h-0">
                                                <div className="h-full overflow-auto p-2">
                                                    <div className="space-y-1">
                                                        {Object.entries(selectedSpan.span.attributes).map(([key, value]) => {
                                                            const isUrl = typeof value === 'string' && (value.startsWith('http://') || value.startsWith('https://'));
                                                            const isNumber = typeof value === 'number' || !isNaN(Number(value));
                                                            const isBoolean = typeof value === 'boolean' || value === 'true' || value === 'false';
                                                            const isJson = typeof value === 'object' || (typeof value === 'string' && (value.startsWith('{') || value.startsWith('[')));

                                                            return (
                                                                <div key={key} className="bg-white rounded p-1.5 border border-gray-200 hover:border-gray-300 transition-all">
                                                                    <div className="flex items-start gap-1.5">
                                                                        {/* Компактная иконка типа */}
                                                                        <div className="flex-shrink-0 mt-0.5">
                                                                            {isUrl ? (
                                                                                <div className="p-0.5 bg-blue-100 rounded">
                                                                                    <Globe className="h-2.5 w-2.5 text-blue-600" />
                                                                                </div>
                                                                            ) : isNumber ? (
                                                                                <div className="p-0.5 bg-green-100 rounded">
                                                                                    <BarChart3 className="h-2.5 w-2.5 text-green-600" />
                                                                                </div>
                                                                            ) : isBoolean ? (
                                                                                <div className="p-0.5 bg-purple-100 rounded">
                                                                                    <CheckCircle className="h-2.5 w-2.5 text-purple-600" />
                                                                                </div>
                                                                            ) : isJson ? (
                                                                                <div className="p-0.5 bg-orange-100 rounded">
                                                                                    <Settings className="h-2.5 w-2.5 text-orange-600" />
                                                                                </div>
                                                                            ) : (
                                                                                <div className="p-0.5 bg-gray-100 rounded">
                                                                                    <Activity className="h-2.5 w-2.5 text-gray-600" />
                                                                                </div>
                                                                            )}
                                                                        </div>

                                                                        {/* Содержимое */}
                                                                        <div className="flex-1 min-w-0">
                                                                            <div className="flex items-center gap-1">
                                                                                <span className="text-sm font-bold text-gray-900 truncate">
                                                                                    {key}
                                                                                </span>
                                                                                <span className={`px-1 py-0.5 text-xs rounded font-medium ${
                                                                                    isUrl ? 'bg-blue-100 text-blue-700' :
                                                                                    isNumber ? 'bg-green-100 text-green-700' :
                                                                                    isBoolean ? 'bg-purple-100 text-purple-700' :
                                                                                    isJson ? 'bg-orange-100 text-orange-700' :
                                                                                    'bg-gray-100 text-gray-700'
                                                                                }`}>
                                                                                    {isUrl ? 'URL' : isNumber ? 'Num' : isBoolean ? 'Bool' : isJson ? 'Obj' : 'Str'}
                                                                                </span>
                                                                            </div>

                                                                            <div className="text-sm mt-0.5">
                                                                                {isUrl ? (
                                                                                    <a
                                                                                        href={value as string}
                                                                                        target="_blank"
                                                                                        rel="noopener noreferrer"
                                                                                        className="text-blue-600 hover:text-blue-800 underline break-all text-xs"
                                                                                    >
                                                                                        {value as string}
                                                                                    </a>
                                                                                ) : isJson && typeof value === 'object' ? (
                                                                                    <div className="bg-gray-50 rounded p-1.5 mt-0.5 border">
                                                                                        <pre className="text-xs text-gray-700 whitespace-pre-wrap overflow-auto max-h-24 leading-tight">
                                                                                            {JSON.stringify(value, null, 2)}
                                                                                        </pre>
                                                                                    </div>
                                                                                ) : isJson && typeof value === 'string' ? (
                                                                                    <div className="bg-gray-50 rounded p-1.5 mt-0.5 border">
                                                                                        <pre className="text-xs text-gray-700 whitespace-pre-wrap overflow-auto max-h-24 leading-tight">
                                                                                            {(() => {
                                                                                                try {
                                                                                                    return JSON.stringify(JSON.parse(value), null, 2);
                                                                                                } catch {
                                                                                                    return value;
                                                                                                }
                                                                                            })()}
                                                                                        </pre>
                                                                                    </div>
                                                                                ) : (
                                                                                    <div className="bg-gray-50 rounded p-1.5 mt-0.5 border">
                                                                                        <span className={`font-mono break-all text-xs leading-tight ${
                                                                                            isNumber ? 'text-green-700 font-semibold' :
                                                                                            isBoolean ? 'text-purple-700 font-semibold' :
                                                                                            'text-gray-700'
                                                                                        }`}>
                                                                                            {String(value)}
                                                                                        </span>
                                                                                    </div>
                                                                                )}
                                                                            </div>
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            );
                                                        })}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex-1 flex items-center justify-center min-h-0">
                                            <div className="text-center text-gray-500">
                                                <Settings className="h-12 w-12 mx-auto mb-4 opacity-50" />
                                                <p className="text-lg font-medium">No attributes available for this span</p>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};
