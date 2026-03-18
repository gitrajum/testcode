import { useState, useEffect } from "react";
import { SettingsState } from "@/a2a/state/settings/SettingsState";
import { AgentCard } from "@/a2a/schema";

export interface TraceNode {
    id: string;
    name: string;
    context: {
        trace_id: string;
        span_id: string;
    };
    span_kind: string;
    parent_id?: string | null;
    start_time: string;
    end_time: string;
    status_code: string;
    status_message: string;
    attributes: Record<string, any>;
    events: Array<{
        name: string;
        timestamp: string;
        attributes: Record<string, any>;
    }>;
}

interface PhoenixProject {
    id: string;
    name: string;
    description?: string;
}

interface UseTraceOptions {
    contextId?: string;
    settings: SettingsState;
    selectedAgent?: AgentCard | null;
    limit?: number;
    startTime?: Date;
    endTime?: Date;
}

export const useTrace = ({ contextId, settings, selectedAgent, limit = 1000, startTime, endTime }: UseTraceOptions) => {
    const [trace, setTrace] = useState<TraceNode[] | null>(null);
    const [loading, setLoading] = useState<boolean>(false);
    const [error, setError] = useState<string | null>(null);
    const [projectId, setProjectId] = useState<string | null>(null);
    const [availableProjects, setAvailableProjects] = useState<PhoenixProject[]>([]);
    const [refreshTrigger, setRefreshTrigger] = useState<number>(0);

    // Функция для принудительного обновления
    const refreshTrace = () => {
        setRefreshTrigger(prev => prev + 1);
    };

    useEffect(() => {
        if (!selectedAgent?.name || !settings.arize_phoenix_enabled || !settings.arize_phoenix_url) {
            setTrace(null);
            setProjectId(null);
            return;
        }

        const fetchTrace = async () => {
            setLoading(true);
            setError(null);
            try {
                // Шаг 1: Получаем список всех проектов
                console.log(`Fetching projects from Phoenix: ${settings.arize_phoenix_url}/v1/projects`);

                const projectsRes = await fetch(`${settings.arize_phoenix_url}/v1/projects`, {
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    }
                });

                if (!projectsRes.ok) {
                    if (projectsRes.status === 403) {
                        throw new Error(`Access denied to Phoenix projects. Check Phoenix permissions.`);
                    } else {
                        const errorText = await projectsRes.text().catch(() => 'Unknown error');
                        throw new Error(`Phoenix API error (${projectsRes.status}): ${errorText}`);
                    }
                }

                const projectsData = await projectsRes.json();
                console.log('Phoenix projects response:', projectsData);

                // Проверяем структуру ответа
                if (!projectsData || !Array.isArray(projectsData.data)) {
                    console.warn('Unexpected projects response format:', projectsData);
                    throw new Error('Invalid projects response format from Phoenix API');
                }

                const projects: PhoenixProject[] = projectsData.data;
                console.log(`Found ${projects.length} projects in Phoenix`);
                setAvailableProjects(projects);

                // Шаг 2: Ищем проект с именем, соответствующим агенту
                const agentName = selectedAgent.name;
                const matchingProject = projects.find(project =>
                    project.name === agentName ||
                    project.name.toLowerCase() === agentName.toLowerCase()
                );

                if (!matchingProject) {
                    console.log(`Available projects: ${projects.map(p => p.name).join(', ')}`);
                    // Вместо выброса ошибки, устанавливаем специальное сообщение об отсутствии проекта
                    const availableProjects = projects.map(p => p.name).join(', ');
                    setError(`Проект не найден для агента "${agentName}". ${projects.length > 0 ? `Доступные проекты: ${availableProjects}` : 'Нет доступных проектов.'}`);
                    setTrace(null);
                    setProjectId(null);
                    setLoading(false);
                    return;
                }

                console.log(`Found matching project: ${matchingProject.name} (ID: ${matchingProject.id})`);
                setProjectId(matchingProject.id);

                // Шаг 3: Получаем спаны с фильтрацией по session_id на стороне Phoenix
                const baseUrl = `${settings.arize_phoenix_url}/v1/projects/${encodeURIComponent(matchingProject.id)}/spans`;
                const params = new URLSearchParams();

                if (limit) {
                    params.append('limit', limit.toString());
                }

                if (startTime) {
                    params.append('start_time', startTime.toISOString());
                }

                if (endTime) {
                    params.append('end_time', endTime.toISOString());
                }

                // Добавляем фильтр по session_id если contextId предоставлен
                if (contextId) {
                    // Используем Phoenix Query DSL для фильтрации по session_id
                    const sessionFilter = `attributes['gcp.vertex.agent.session_id'] == '${contextId}' or attributes['session_id'] == '${contextId}' or attributes['session.id'] == '${contextId}' or attributes['sessionId'] == '${contextId}'`;
                    params.append('filter', sessionFilter);
                    console.log(`Applying session filter: ${sessionFilter}`);
                }

                const spansUrl = `${baseUrl}?${params.toString()}`;
                console.log(`Fetching spans from: ${spansUrl}`);

                const spansRes = await fetch(spansUrl, {
                    headers: {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json'
                    }
                });

                if (!spansRes.ok) {
                    if (spansRes.status === 404) {
                        throw new Error(`Spans not found for project "${matchingProject.name}".`);
                    } else if (spansRes.status === 403) {
                        throw new Error(`Access denied to spans for project "${matchingProject.name}".`);
                    } else {
                        const errorText = await spansRes.text().catch(() => 'Unknown error');
                        throw new Error(`Phoenix spans API error (${spansRes.status}): ${errorText}`);
                    }
                }

                const spansData = await spansRes.json();
                console.log(`Received ${spansData?.data?.length || 0} spans for project "${matchingProject.name}"`);

                // Проверяем структуру ответа согласно SpansResponseBody
                if (spansData && Array.isArray(spansData.data)) {
                    let filteredSpans = spansData.data;

                    if (contextId && filteredSpans.length > 0) {
                        console.log(`Found ${filteredSpans.length} spans with session_id: ${contextId}`);

                        // Группируем спаны по trace_id для получения полных трейсов
                        const traceGroups = new Map<string, TraceNode[]>();
                        filteredSpans.forEach((span: TraceNode) => {
                            const traceId = span.context.trace_id;
                            if (!traceGroups.has(traceId)) {
                                traceGroups.set(traceId, []);
                            }
                            traceGroups.get(traceId)!.push(span);
                        });

                        console.log(`Found ${traceGroups.size} unique traces with session spans`);

                        // Если у нас есть неполные трейсы, получаем недостающие спаны
                        const allTraceIds = Array.from(traceGroups.keys());
                        const incompleteTraces: string[] = [];

                        // Проверяем каждый трейс на полноту
                        for (const [traceId, spans] of traceGroups.entries()) {
                            const hasOrphanSpans = spans.some(span =>
                                span.parent_id && !spans.find(s => s.context.span_id === span.parent_id)
                            );
                            if (hasOrphanSpans) {
                                incompleteTraces.push(traceId);
                            }
                        }

                        console.log(`Found ${incompleteTraces.length} incomplete traces that need additional spans`);

                        // Получаем недостающие спаны для неполных трейсов
                        if (incompleteTraces.length > 0) {
                            for (const traceId of incompleteTraces) {
                                try {
                                    const traceParams = new URLSearchParams();
                                    traceParams.append('limit', '1000'); // Увеличиваем лимит для полного трейса
                                    traceParams.append('filter', `context.trace_id == '${traceId}'`);

                                    const traceUrl = `${baseUrl}?${traceParams.toString()}`;
                                    console.log(`Fetching complete trace ${traceId}: ${traceUrl}`);

                                    const traceRes = await fetch(traceUrl, {
                                        headers: {
                                            'Accept': 'application/json',
                                            'Content-Type': 'application/json'
                                        }
                                    });

                                    if (traceRes.ok) {
                                        const traceData = await traceRes.json();
                                        if (traceData && Array.isArray(traceData.data)) {
                                            // Заменяем неполный трейс полным
                                            traceGroups.set(traceId, traceData.data);
                                            console.log(`Updated trace ${traceId} with ${traceData.data.length} spans`);
                                        }
                                    }
                                } catch (err) {
                                    console.warn(`Failed to fetch complete trace ${traceId}:`, err);
                                }
                            }
                        }

                        // ВАЖНО: Фильтруем трейсы - оставляем только те, которые содержат спаны с нашим session_id
                        const sessionTraceGroups = new Map<string, TraceNode[]>();

                        traceGroups.forEach((spans, traceId) => {
                            // Проверяем, есть ли в этом трейсе хотя бы один спан с нашим session_id
                            const hasSessionSpan = spans.some(span =>
                                span.attributes?.['gcp.vertex.agent.session_id'] === contextId ||
                                span.attributes?.session_id === contextId ||
                                span.attributes?.['session.id'] === contextId ||
                                span.attributes?.sessionId === contextId
                            );

                            if (hasSessionSpan) {
                                sessionTraceGroups.set(traceId, spans);
                            }
                        });

                        console.log(`After session filtering: ${sessionTraceGroups.size} traces (was ${traceGroups.size})`);

                        // Объединяем все спаны из трейсов, содержащих session spans
                        const allSpans: TraceNode[] = Array.from(sessionTraceGroups.values()).flat();

                        // Дедупликация спанов по ID
                        const uniqueSpansMap = new Map<string, TraceNode>();
                        for (const span of allSpans) {
                            uniqueSpansMap.set(span.id, span);
                        }

                        filteredSpans = Array.from(uniqueSpansMap.values());

                        // Сортируем по времени начала
                        filteredSpans.sort((a: TraceNode, b: TraceNode) =>
                            new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
                        );

                        console.log(`After deduplication: ${filteredSpans.length} unique spans (was ${allSpans.length})`);

                        // Проверяем на дублирующиеся ID
                        const spanIds = filteredSpans.map((span: TraceNode) => span.id);
                        const uniqueIds = new Set(spanIds);
                        if (spanIds.length !== uniqueIds.size) {
                            console.warn(`Found ${spanIds.length - uniqueIds.size} duplicate span IDs after deduplication!`);
                        }

                        console.log(`Final result: ${filteredSpans.length} spans from ${sessionTraceGroups.size} session traces`);

                        // Логируем структуру трейсов с session spans
                        sessionTraceGroups.forEach((spans, traceId) => {
                            const sessionSpans = spans.filter(span =>
                                span.attributes?.['gcp.vertex.agent.session_id'] === contextId ||
                                span.attributes?.session_id === contextId ||
                                span.attributes?.['session.id'] === contextId ||
                                span.attributes?.sessionId === contextId
                            );
                            const rootSpans = spans.filter(span => !span.parent_id || !spans.find(s => s.context.span_id === span.parent_id));
                            console.log(`Trace ${traceId.substring(0, 8)}: ${spans.length} spans (${sessionSpans.length} session), ${rootSpans.length} roots`);
                        });
                    } else if (contextId) {
                        console.log('No spans found with the specified session_id');
                        console.log('Available session_ids in spans:',
                            spansData.data.map((span: TraceNode) =>
                                span.attributes?.['gcp.vertex.agent.session_id'] ||
                                span.attributes?.session_id ||
                                span.attributes?.['session.id'] ||
                                span.attributes?.sessionId || 'none'
                            ).filter((id: string, index: number, arr: string[]) => arr.indexOf(id) === index)
                        );
                        filteredSpans = [];
                    }

                    setTrace(filteredSpans);
                } else {
                    console.warn('Unexpected spans response format:', spansData);
                    setTrace([]);
                }
            } catch (err) {
                console.error('Phoenix API error:', err);
                setError(err instanceof Error ? err.message : String(err));
                setTrace(null);
                setProjectId(null);
            } finally {
                setLoading(false);
            }
        };

        fetchTrace();
    }, [selectedAgent?.name, settings, limit, startTime, endTime, contextId, refreshTrigger]);

    return { trace, loading, error, projectId, availableProjects, refreshTrace };
};
