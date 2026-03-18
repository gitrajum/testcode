import React from 'react';
import { TraceNode } from '@/hooks/useTrace';
import {
    ChevronLeft,
    ChevronRight,
    Activity,
    Clock,
    Zap,
    AlertCircle,
    Database,
    Cpu,
    Globe,
    Settings,
    CheckCircle,
    XCircle,
    AlertTriangle,
    Timer,
    BarChart3,
    Eye,
    EyeOff,
    Maximize2,
    Minimize2,
    ExternalLink,
    Hash,
    ToggleLeft,
    Braces,
    Type
} from 'lucide-react';
import styles from './TraceGraph.module.css';

interface TraceGraphProps {
    trace: TraceNode[];
    contextId?: string;
}

interface GraphNode {
    id: string;
    name: string;
    span: TraceNode;
    x: number;
    y: number;
    level: number;
    children: string[];
    parents: string[];
    isSessionSpan: boolean;
}

interface GraphEdge {
    from: string;
    to: string;
    fromX: number;
    fromY: number;
    toX: number;
    toY: number;
}

interface ProcessedTrace {
    traceId: string;
    nodes: GraphNode[];
    edges: GraphEdge[];
    sessionSpansCount: number;
    totalSpans: number;
    bounds: {
        minX: number;
        maxX: number;
        minY: number;
        maxY: number;
        width: number;
        height: number;
    };
}

export const TraceGraph: React.FC<TraceGraphProps> = ({ trace, contextId }) => {
    const [selectedNode, setSelectedNode] = React.useState<GraphNode | null>(null);
    const [currentTraceIndex, setCurrentTraceIndex] = React.useState(0);
    const [hoveredNode, setHoveredNode] = React.useState<string | null>(null);

    // Используем состояние для предотвращения hydration mismatch
    const [isClient, setIsClient] = React.useState(false);

    React.useEffect(() => {
        setIsClient(true);
    }, []);

    const containerRef = React.useRef<HTMLDivElement>(null);
    const svgRef = React.useRef<SVGSVGElement>(null);

    // Адаптивные константы для layout
    const NODE_WIDTH = 140;
    const NODE_HEIGHT = 40;
    const LEVEL_HEIGHT = 60;
    const NODE_SPACING = 15;
    const PADDING = 15;

    // Проверка является ли span сессионным
    const isSessionSpan = React.useCallback((span: TraceNode): boolean => {
        if (!contextId) return false;

        const sessionId = span.attributes?.session_id ||
                         span.attributes?.['session.id'] ||
                         span.attributes?.sessionId ||
                         span.attributes?.['gcp.vertex.agent.session_id'];

        return sessionId === contextId;
    }, [contextId]);

    // Построение графа для одного trace
    const buildTraceGraph = React.useCallback((traceId: string, spans: TraceNode[]): ProcessedTrace => {
        console.log(`\n=== Building trace graph for ${traceId} ===`);
        console.log(`Total spans: ${spans.length}`);

        // Шаг 1: Создаем карту всех узлов
        const allNodesMap = new Map<string, GraphNode>();
        spans.forEach(span => {
            const node: GraphNode = {
                id: span.id,
                name: span.name,
                span: span,
                x: 0,
                y: 0,
                level: 0,
                children: [],
                parents: [],
                isSessionSpan: isSessionSpan(span)
            };
            allNodesMap.set(span.id, node);
        });
        console.log(`Created ${allNodesMap.size} nodes`);

        // Шаг 2: Строим граф по parent_id
        console.log('TraceGraph: All span IDs and parent_ids:');
        spans.forEach(span => {
            console.log(`  ${span.name}: id=${span.id}, context.span_id=${span.context.span_id}, parent_id=${span.parent_id}`);
        });

        allNodesMap.forEach(node => {
            const parentId = node.span.parent_id;
            if (parentId) {
                // Пробуем найти родителя по разным полям
                let parent = allNodesMap.get(parentId); // Сначала по span.id
                if (!parent) {
                    // Если не найден, ищем по context.span_id
                    for (const [_, candidateNode] of allNodesMap) {
                        if (candidateNode.span.context.span_id === parentId) {
                            parent = candidateNode;
                            break;
                        }
                    }
                }

                if (parent) {
                    parent.children.push(node.id);
                    node.parents.push(parent.id);
                    console.log(`TraceGraph: Linked ${node.name} to parent ${parent.name}`);
                } else {
                    console.log(`TraceGraph: Parent not found for ${node.name} (parent_id: ${parentId})`);
                }
            }
        });

        // Логируем структуру графа
        const rootNodes = Array.from(allNodesMap.values()).filter(node => node.parents.length === 0);
        console.log(`TraceGraph: Built hierarchy - ${rootNodes.length} root nodes`);
        rootNodes.forEach(root => {
            console.log(`  Root: ${root.name} (${root.children.length} children)`);
        });

        // Ищем стартовый спан DefaultRequestHandler._run_event_stream
        const startSpanName = 'a2a.server.request_handlers.default_request_handler.DefaultRequestHandler._run_event_stream';
        const startSpan = spans.find(span => span.name === startSpanName);

        if (!startSpan) {
            console.log(`TraceGraph: Start span "${startSpanName}" not found in trace`);
        } else {
            console.log(`TraceGraph: Found start span "${startSpanName}" (${startSpan.id})`);
        }

        // Выбираем главный корневой узел (приоритет стартового спана)
        let mainRootNode: GraphNode | undefined;
        let filteredNodes = Array.from(allNodesMap.values());

        // Сначала ищем стартовый спан
        if (startSpan) {
            const startNode = allNodesMap.get(startSpan.id);
            if (startNode) {
                mainRootNode = startNode;
                console.log(`TraceGraph: Using start span as single root, showing only its subtree`);
                console.log(`TraceGraph: Start span has ${startNode.children.length} direct children`);

                // Логируем структуру дерева
                const logNodeTree = (node: GraphNode, indent = '') => {
                    console.log(`${indent}${node.name} (${node.id}) - children: ${node.children.length}`);
                    node.children.forEach(childId => {
                        const child = allNodesMap.get(childId);
                        if (child) {
                            logNodeTree(child, indent + '  ');
                        }
                    });
                };
                logNodeTree(startNode);

                // Собираем только узлы из поддерева стартового спана
                const collectSubtreeNodes = (node: GraphNode): GraphNode[] => {
                    const result = [node];
                    node.children.forEach(childId => {
                        const child = allNodesMap.get(childId);
                        if (child) {
                            result.push(...collectSubtreeNodes(child));
                        }
                    });
                    return result;
                };

                filteredNodes = collectSubtreeNodes(startNode);
                console.log(`TraceGraph: Collected ${filteredNodes.length} nodes from DefaultRequestHandler subtree`);

                // Обновляем allNodesMap чтобы содержать только узлы из поддерева
                allNodesMap.clear();
                filteredNodes.forEach(node => {
                    allNodesMap.set(node.id, node);
                });

                // Пересчитываем корневые узлы (теперь только стартовый спан)
                const newRootNodes = filteredNodes.filter(node =>
                    !node.parents.length || !filteredNodes.some(n => n.children.includes(node.id))
                );
                console.log(`TraceGraph: New root nodes count: ${newRootNodes.length}`);
            }
        }

        // Если стартовый спан не найден, используем обычную логику
        if (!mainRootNode) {
            mainRootNode = rootNodes.find(node => node.isSessionSpan);
            if (mainRootNode) {
                console.log(`TraceGraph: Using session span as main root node`);
            }
        }

                 // Если и session span не найден, берем самый ранний по времени
         if (!mainRootNode) {
             mainRootNode = rootNodes.sort((a, b) => {
                 const aTime = new Date(a.span.start_time).getTime();
                 const bTime = new Date(b.span.start_time).getTime();
                 return aTime - bTime;
             })[0];
             if (mainRootNode) {
                 console.log(`TraceGraph: Using earliest span as main root node`);
             }
         }

        if (!mainRootNode) {
            console.log('No root node found, returning empty graph');
            return {
                traceId,
                nodes: [],
                edges: [],
                sessionSpansCount: 0,
                totalSpans: 0,
                bounds: { minX: 0, maxX: 100, minY: 0, maxY: 100, width: 100, height: 100 }
            };
        }

        // Собираем все узлы, начиная с найденного корня
        const collectSubtree = (nodeId: string, visited = new Set<string>()): GraphNode[] => {
            if (visited.has(nodeId)) return [];
            visited.add(nodeId);

            const node = allNodesMap.get(nodeId);
            if (!node) return [];

            const subtree = [node];
            node.children.forEach(childId => {
                subtree.push(...collectSubtree(childId, visited));
            });

            return subtree;
        };

        let nodes = collectSubtree(mainRootNode.id);

        // Если поддерево содержит только один узел, попробуем включить связанные session узлы
        if (nodes.length === 1 && contextId) {
            const allSessionNodes = Array.from(allNodesMap.values()).filter(node => {
                const sessionId = node.span.attributes?.session_id ||
                                 node.span.attributes?.['session.id'] ||
                                 node.span.attributes?.sessionId ||
                                 node.span.attributes?.['gcp.vertex.agent.session_id'];
                return sessionId === contextId;
            });

            if (allSessionNodes.length > 1) {
                nodes = allSessionNodes;
                console.log(`Extended to include all ${allSessionNodes.length} session nodes`);
            }
        }

        const nodeMap = new Map<string, GraphNode>();
        nodes.forEach(node => nodeMap.set(node.id, node));

        console.log(`Collected ${nodes.length} nodes in subtree`);

        // Пересчитываем связи только для выбранных узлов
        nodes.forEach(node => {
            node.children = node.children.filter(childId => nodeMap.has(childId));
            node.parents = node.parents.filter(parentId => nodeMap.has(parentId));
        });

        // Вычисляем уровни от выбранного корня
        const calculateLevels = (nodeId: string, level: number, visited = new Set<string>()) => {
            if (visited.has(nodeId)) return;
            visited.add(nodeId);

            const node = nodeMap.get(nodeId);
            if (!node) return;

            node.level = level;
            node.children.forEach(childId => {
                calculateLevels(childId, level + 1, visited);
            });
        };

        // Начинаем с выбранного корня на уровне 0
        calculateLevels(mainRootNode.id, 0);

        // Обрабатываем узлы без уровня (изолированные)
        nodes.forEach(node => {
            if (node.level === -1) {
                node.level = 0; // Помещаем изолированные узлы на уровень 0
            }
        });

        // Группируем узлы по уровням
        const levelGroups = new Map<number, GraphNode[]>();
        nodes.forEach(node => {
            if (!levelGroups.has(node.level)) {
                levelGroups.set(node.level, []);
            }
            levelGroups.get(node.level)!.push(node);
        });

        // Простое вертикальное позиционирование дерева
        const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);

        // Позиционируем узлы уровень за уровнем
        sortedLevels.forEach(level => {
            const levelNodes = levelGroups.get(level)!;

            if (level === 0) {
                // Корневые узлы - центрируем горизонтально
                const totalWidth = Math.max(0, (levelNodes.length - 1) * (NODE_WIDTH + NODE_SPACING));
                const startX = -totalWidth / 2;

                levelNodes.forEach((node, index) => {
                    node.x = startX + index * (NODE_WIDTH + NODE_SPACING);
                    node.y = 0; // Корневые узлы на самом верху
                });

                console.log(`Level ${level} (root): positioned ${levelNodes.length} nodes`);
            } else {
                // Дочерние узлы - позиционируем под родителями
                let nextX = 0;

                levelNodes.forEach(node => {
                    if (node.parents.length > 0) {
                        const parentId = node.parents[0];
                        const parent = nodeMap.get(parentId);

                        if (parent) {
                            // Позиционируем под родителем с небольшим смещением
                            node.x = parent.x;
                            node.y = level * LEVEL_HEIGHT;
                        } else {
                            // Если родитель не найден, позиционируем последовательно
                            node.x = nextX;
                            node.y = level * LEVEL_HEIGHT;
                            nextX += NODE_WIDTH + NODE_SPACING;
                        }
                    } else {
                        // Узел без родителя - позиционируем последовательно
                        node.x = nextX;
                        node.y = level * LEVEL_HEIGHT;
                        nextX += NODE_WIDTH + NODE_SPACING;
                    }
                });

                // Исправляем пересечения на уровне
                const sortedNodes = levelNodes.slice().sort((a, b) => a.x - b.x);
                for (let i = 1; i < sortedNodes.length; i++) {
                    const prevNode = sortedNodes[i - 1];
                    const currentNode = sortedNodes[i];
                    const minDistance = NODE_WIDTH + NODE_SPACING; // Минимальное расстояние

                    if (currentNode.x - prevNode.x < minDistance) {
                        const shift = minDistance - (currentNode.x - prevNode.x);
                        // Сдвигаем текущий и все последующие узлы
                        for (let j = i; j < sortedNodes.length; j++) {
                            sortedNodes[j].x += shift;
                        }
                    }
                }

                console.log(`Level ${level}: positioned ${levelNodes.length} nodes`);
            }
        });

        // Создаем рёбра
        const edges: GraphEdge[] = [];
        nodes.forEach(node => {
            node.children.forEach(childId => {
                const child = nodeMap.get(childId);
                if (child) {
                    edges.push({
                        from: node.id,
                        to: child.id,
                        fromX: node.x + NODE_WIDTH / 2,
                        fromY: node.y + NODE_HEIGHT,
                        toX: child.x + NODE_WIDTH / 2,
                        toY: child.y
                    });
                }
            });
        });

        console.log(`Created ${edges.length} edges:`, edges.slice(0, 3).map(e => ({
            from: e.from,
            to: e.to,
            fromX: e.fromX,
            fromY: e.fromY,
            toX: e.toX,
            toY: e.toY
        })));

        // Вычисляем границы
        const minX = Math.min(...nodes.map(n => n.x)) - PADDING;
        const maxX = Math.max(...nodes.map(n => n.x + NODE_WIDTH)) + PADDING;
        const minY = Math.min(...nodes.map(n => n.y)) - PADDING;
        const maxY = Math.max(...nodes.map(n => n.y + NODE_HEIGHT)) + PADDING;

        console.log(`Final bounds: minX=${minX}, maxX=${maxX}, minY=${minY}, maxY=${maxY}`);
        console.log(`Final node positions:`, nodes.map(n => ({ id: n.id, x: n.x, y: n.y, level: n.level })));

        const sessionSpansCount = nodes.filter(n => n.isSessionSpan).length;

        console.log(`TraceGraph: Final result - ${nodes.length} nodes for display`);
        console.log(`TraceGraph: Nodes:`, nodes.map(n => ({ name: n.name, level: n.level, children: n.children.length })));

        // Фильтруем узлы - исключаем те, которые содержат "a2a.server" в названии
        const finalFilteredNodes = nodes.filter(node => !node.name.includes('a2a.server'));
        console.log(`TraceGraph: After filtering out a2a.server nodes: ${finalFilteredNodes.length} nodes (was ${nodes.length})`);

        // Обновляем связи между отфильтрованными узлами
        const finalFilteredNodeIds = new Set(finalFilteredNodes.map(n => n.id));
        finalFilteredNodes.forEach(node => {
            node.children = node.children.filter(childId => finalFilteredNodeIds.has(childId));
            node.parents = node.parents.filter(parentId => finalFilteredNodeIds.has(parentId));
        });

        // Пересчитываем уровни для отфильтрованных узлов
        const recalculateLevels = (nodes: GraphNode[]) => {
            // Находим корневые узлы среди отфильтрованных
            const rootNodes = nodes.filter(node => node.parents.length === 0 || !nodes.some(n => n.children.includes(node.id)));

            // Пересчитываем уровни от корневых узлов
            const visited = new Set<string>();
            const calculateLevel = (nodeId: string, level: number) => {
                if (visited.has(nodeId)) return;
                visited.add(nodeId);

                const node = nodes.find(n => n.id === nodeId);
                if (!node) return;

                node.level = level;
                node.children.forEach(childId => {
                    calculateLevel(childId, level + 1);
                });
            };

            rootNodes.forEach(root => calculateLevel(root.id, 0));
        };

        if (finalFilteredNodes.length > 0) {
            recalculateLevels(finalFilteredNodes);
        }

        // Пересчитываем позиции для отфильтрованных узлов
        if (finalFilteredNodes.length > 0) {
            // Группируем по уровням
            const levelGroups = new Map<number, GraphNode[]>();
            finalFilteredNodes.forEach(node => {
                if (!levelGroups.has(node.level)) {
                    levelGroups.set(node.level, []);
                }
                levelGroups.get(node.level)!.push(node);
            });

            // Позиционируем узлы уровень за уровнем
            const sortedLevels = Array.from(levelGroups.keys()).sort((a, b) => a - b);

            sortedLevels.forEach(level => {
                const levelNodes = levelGroups.get(level)!;

                if (level === 0) {
                    // Корневые узлы - центрируем горизонтально
                    const totalWidth = Math.max(0, (levelNodes.length - 1) * (NODE_WIDTH + NODE_SPACING));
                    const startX = -totalWidth / 2;

                    levelNodes.forEach((node, index) => {
                        node.x = startX + index * (NODE_WIDTH + NODE_SPACING);
                        node.y = 0;
                    });
                } else {
                    // Дочерние узлы - позиционируем под родителями
                    let nextX = 0;

                    levelNodes.forEach(node => {
                        if (node.parents.length > 0) {
                            const parentId = node.parents[0];
                            const parent = finalFilteredNodes.find(n => n.id === parentId);

                            if (parent) {
                                node.x = parent.x;
                                node.y = level * LEVEL_HEIGHT;
                            } else {
                                node.x = nextX;
                                node.y = level * LEVEL_HEIGHT;
                                nextX += NODE_WIDTH + NODE_SPACING;
                            }
                        } else {
                            node.x = nextX;
                            node.y = level * LEVEL_HEIGHT;
                            nextX += NODE_WIDTH + NODE_SPACING;
                        }
                    });

                    // Исправляем пересечения на уровне
                    const sortedNodes = levelNodes.slice().sort((a, b) => a.x - b.x);
                    for (let i = 1; i < sortedNodes.length; i++) {
                        const prevNode = sortedNodes[i - 1];
                        const currentNode = sortedNodes[i];
                        const minDistance = NODE_WIDTH + NODE_SPACING;

                        if (currentNode.x - prevNode.x < minDistance) {
                            const shift = minDistance - (currentNode.x - prevNode.x);
                            for (let j = i; j < sortedNodes.length; j++) {
                                sortedNodes[j].x += shift;
                            }
                        }
                    }
                }
            });
        }

        // Создаем рёбра для отфильтрованных узлов
        const finalFilteredEdges: GraphEdge[] = [];
        finalFilteredNodes.forEach(node => {
            node.children.forEach(childId => {
                const child = finalFilteredNodes.find(n => n.id === childId);
                if (child) {
                    finalFilteredEdges.push({
                        from: node.id,
                        to: child.id,
                        fromX: node.x + NODE_WIDTH / 2,
                        fromY: node.y + NODE_HEIGHT,
                        toX: child.x + NODE_WIDTH / 2,
                        toY: child.y
                    });
                }
            });
        });

        console.log(`TraceGraph: Created ${finalFilteredEdges.length} edges for filtered nodes`);

        // Вычисляем границы для отфильтрованных узлов
        let finalMinX = 0, finalMaxX = 100, finalMinY = 0, finalMaxY = 100;
        if (finalFilteredNodes.length > 0) {
            finalMinX = Math.min(...finalFilteredNodes.map(n => n.x)) - PADDING;
            finalMaxX = Math.max(...finalFilteredNodes.map(n => n.x + NODE_WIDTH)) + PADDING;
            finalMinY = Math.min(...finalFilteredNodes.map(n => n.y)) - PADDING;
            finalMaxY = Math.max(...finalFilteredNodes.map(n => n.y + NODE_HEIGHT)) + PADDING;
        }

        console.log(`TraceGraph: Final filtered bounds: minX=${finalMinX}, maxX=${finalMaxX}, minY=${finalMinY}, maxY=${finalMaxY}`);

        const finalSessionSpansCount = finalFilteredNodes.filter(n => n.isSessionSpan).length;

        return {
            traceId,
            nodes: finalFilteredNodes,
            edges: finalFilteredEdges,
            sessionSpansCount: finalSessionSpansCount,
            totalSpans: spans.length,
            bounds: {
                minX: finalMinX,
                maxX: finalMaxX,
                minY: finalMinY,
                maxY: finalMaxY,
                width: finalMaxX - finalMinX,
                height: finalMaxY - finalMinY
            }
        };
    }, [isSessionSpan]);

    // Обработка и построение графов
    const processedTraces = React.useMemo(() => {
        if (!trace.length) return [];

        // Группируем по trace_id
        const traceGroups = new Map<string, TraceNode[]>();
        trace.forEach(span => {
            const traceId = span.context.trace_id;
            if (!traceGroups.has(traceId)) {
                traceGroups.set(traceId, []);
            }
            traceGroups.get(traceId)!.push(span);
        });

        console.log(`TraceGraph: Found ${traceGroups.size} unique traces before session filtering`);

        // Фильтруем трейсы - оставляем только те, которые содержат спаны с session_id (как в JaegerTraceView)
        const sessionTraceGroups = new Map<string, TraceNode[]>();

        traceGroups.forEach((spans, traceId) => {
            // Проверяем, есть ли в этом трейсе хотя бы один спан с нашим session_id
            const sessionSpansCount = spans.filter(span =>
                contextId && (
                    span.attributes?.session_id === contextId ||
                    span.attributes?.['session.id'] === contextId ||
                    span.attributes?.sessionId === contextId ||
                    span.attributes?.['gcp.vertex.agent.session_id'] === contextId
                )
            ).length;

            // Показываем только трейсы, которые содержат session spans (если contextId указан)
            const shouldInclude = !contextId || sessionSpansCount > 0;

            if (shouldInclude) {
                sessionTraceGroups.set(traceId, spans);
                console.log(`TraceGraph: Including trace ${traceId} with ${spans.length} spans (${sessionSpansCount} session)`);
            } else {
                console.log(`TraceGraph: Excluding trace ${traceId} - no session spans found`);
            }
        });

        console.log(`TraceGraph: After session filtering: ${sessionTraceGroups.size} traces (was ${traceGroups.size})`);

        return Array.from(sessionTraceGroups.entries())
            .map(([traceId, spans]) => {
                // Сортируем спаны по времени для правильного порядка
                const sortedSpans = spans.sort((a, b) => {
                    const aTime = new Date(a.start_time).getTime();
                    const bTime = new Date(b.start_time).getTime();
                    return aTime - bTime;
                });

                console.log(`TraceGraph: Building graph for trace ${traceId} with ${sortedSpans.length} spans`);
                return buildTraceGraph(traceId, sortedSpans);
            })
            .sort((a, b) => {
                // Сортируем трейсы по времени начала (как в JaegerTraceView)
                const aStartTime = Math.min(...a.nodes.map(n => new Date(n.span.start_time).getTime()));
                const bStartTime = Math.min(...b.nodes.map(n => new Date(n.span.start_time).getTime()));
                return aStartTime - bStartTime;
            });
    }, [trace, contextId, buildTraceGraph]);

    // Автоматически выбираем последний трейс при обновлении данных
    React.useEffect(() => {
        if (processedTraces.length > 0) {
            const latestTraceIndex = processedTraces.length - 1;
            console.log(`TraceGraph: Auto-selecting latest trace (index ${latestTraceIndex} of ${processedTraces.length})`);
            setCurrentTraceIndex(latestTraceIndex);
        }
    }, [processedTraces]);

    // Текущий trace
    const currentTrace = processedTraces[currentTraceIndex];

    // Навигация
    const goToPreviousTrace = React.useCallback(() => {
        setCurrentTraceIndex(prev => prev > 0 ? prev - 1 : processedTraces.length - 1);
        setSelectedNode(null);
    }, [processedTraces.length]);

    const goToNextTrace = React.useCallback(() => {
        setCurrentTraceIndex(prev => prev < processedTraces.length - 1 ? prev + 1 : 0);
        setSelectedNode(null);
    }, [processedTraces.length]);

    // Скролл к session span
    const scrollToSessionSpan = React.useCallback(() => {
        if (!currentTrace || !containerRef.current || !svgRef.current) return;

        const sessionSpan = currentTrace.nodes.find(node => node.isSessionSpan);
        if (!sessionSpan) return;

        const container = containerRef.current;
        const svg = svgRef.current;
        const svgRect = svg.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();

        // Вычисляем масштаб
        const scaleX = svgRect.width / currentTrace.bounds.width;
        const scaleY = svgRect.height / currentTrace.bounds.height;

        // Позиция узла в SVG координатах
        const nodeX = sessionSpan.x + NODE_WIDTH / 2;
        const nodeY = sessionSpan.y + NODE_HEIGHT / 2;

        // Преобразуем в координаты контейнера
        const scaledX = (nodeX - currentTrace.bounds.minX) * scaleX;
        const scaledY = (nodeY - currentTrace.bounds.minY) * scaleY;

        // Центрируем
        const targetScrollLeft = scaledX - containerRect.width / 2;
        const targetScrollTop = scaledY - containerRect.height / 2;

        container.scrollTo({
            left: Math.max(0, targetScrollLeft),
            top: Math.max(0, targetScrollTop),
            behavior: 'smooth'
        });
    }, [currentTrace]);

    // Автоскролл при смене trace
    React.useEffect(() => {
        const timer = setTimeout(scrollToSessionSpan, 300);
        return () => clearTimeout(timer);
    }, [currentTraceIndex, scrollToSessionSpan]);

    // Обработчики событий
    const handleNodeClick = React.useCallback((node: GraphNode) => {
        setSelectedNode(prev => prev?.id === node.id ? null : node);
    }, []);

    const handleNodeHover = React.useCallback((nodeId: string | null) => {
        setHoveredNode(nodeId);
    }, []);

    // Стили узлов
    const getNodeStyle = React.useCallback((node: GraphNode) => {
        if (selectedNode?.id === node.id) {
            return 'fill-purple-500 stroke-purple-700 stroke-2';
        }
        if (node.isSessionSpan) {
            return 'fill-blue-500 stroke-blue-700 stroke-2';
        }
        switch (node.span.status_code) {
            case 'OK':
                return 'fill-green-500 stroke-green-700 stroke-2';
            case 'ERROR':
                return 'fill-red-500 stroke-red-700 stroke-2';
            default:
                return 'fill-gray-500 stroke-gray-700 stroke-2';
        }
    }, [selectedNode]);

    // Форматирование времени
    const formatDuration = React.useCallback((startTime: string, endTime: string) => {
        const duration = new Date(endTime).getTime() - new Date(startTime).getTime();
        if (duration < 1000) return `${duration}ms`;
        if (duration < 60000) return `${(duration / 1000).toFixed(2)}s`;
        return `${(duration / 60000).toFixed(2)}m`;
    }, []);

    // Обрезка текста
    const truncateText = React.useCallback((text: string, maxLength: number = 18) => {
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    }, []);

    if (!isClient) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-500">
                Loading trace visualization...
            </div>
        );
    }

    if (!processedTraces.length) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-500">
                No trace data available
            </div>
        );
    }

    if (!currentTrace) {
        return (
            <div className="flex items-center justify-center h-64 text-gray-500">
                No trace selected
            </div>
        );
    }

    return (
        <div className="w-full h-full flex flex-col bg-gray-50">
            {/* Компактный заголовок с навигацией */}
            <div className="flex items-center justify-between p-3 bg-white border-b border-gray-200 flex-shrink-0">
                <button
                    onClick={goToPreviousTrace}
                    disabled={processedTraces.length <= 1}
                    className="flex items-center gap-1 px-2 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors"
                >
                    <ChevronLeft className="h-3 w-3" />
                    Prev
                </button>

                <div className="flex flex-col items-center">
                    <div className="text-base font-bold text-gray-800">
                        Graph {currentTraceIndex + 1}/{processedTraces.length}
                    </div>
                    <div className="text-xs text-gray-600 flex items-center gap-2">
                        <span>{currentTrace.traceId.substring(0, 12)}...</span>
                        <span>({currentTrace.sessionSpansCount}s/{currentTrace.totalSpans}t)</span>
                        {contextId && (
                            <span className="px-1.5 py-0.5 text-xs bg-green-100 text-green-800 rounded">
                                Session
                            </span>
                        )}
                    </div>
                </div>

                <button
                    onClick={goToNextTrace}
                    disabled={processedTraces.length <= 1}
                    className="flex items-center gap-1 px-2 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed rounded transition-colors"
                >
                    Next
                    <ChevronRight className="h-3 w-3" />
                </button>
            </div>

            {/* Основной контент */}
            <div className="flex-1 flex flex-col min-h-0">
                {/* Граф - уменьшается когда выбран узел */}
                <div className={`${selectedNode ? 'h-1/3' : 'flex-1'} min-h-0 border-b border-gray-200`}>
                    <div
                        ref={containerRef}
                        className="w-full h-full overflow-auto bg-white"
                    >
                        <div className="w-full h-full p-4">
                            <svg
                                ref={svgRef}
                                width="100%"
                                height="100%"
                                viewBox={`${currentTrace.bounds.minX} ${currentTrace.bounds.minY} ${currentTrace.bounds.width} ${currentTrace.bounds.height}`}
                                preserveAspectRatio="xMidYMin meet"
                                className="block"
                            >
                                {/* Определения */}
                                <defs>
                                    {/* Градиент для обычных соединений */}
                                    <linearGradient id="connectionGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                        <stop offset="0%" stopColor="#4F46E5" stopOpacity="0.8"/>
                                        <stop offset="100%" stopColor="#7C3AED" stopOpacity="0.6"/>
                                    </linearGradient>

                                    {/* Градиент для session соединений */}
                                    <linearGradient id="sessionConnectionGradient" x1="0%" y1="0%" x2="0%" y2="100%">
                                        <stop offset="0%" stopColor="#F59E0B" stopOpacity="0.9"/>
                                        <stop offset="50%" stopColor="#EF4444" stopOpacity="0.8"/>
                                        <stop offset="100%" stopColor="#EC4899" stopOpacity="0.7"/>
                                    </linearGradient>

                                    {/* Красивая стрелка */}
                                    <marker
                                        id="arrowhead"
                                        markerWidth="12"
                                        markerHeight="8"
                                        refX="11"
                                        refY="4"
                                        orient="auto"
                                        markerUnits="strokeWidth"
                                    >
                                        <path
                                            d="M 0 0 L 12 4 L 0 8 L 3 4 Z"
                                            fill="#4F46E5"
                                            stroke="#4F46E5"
                                            strokeWidth="0.5"
                                            strokeLinejoin="round"
                                        />
                                    </marker>

                                    {/* Стрелка для hover состояния */}
                                    <marker
                                        id="arrowhead-hover"
                                        markerWidth="12"
                                        markerHeight="8"
                                        refX="11"
                                        refY="4"
                                        orient="auto"
                                        markerUnits="strokeWidth"
                                    >
                                        <path
                                            d="M 0 0 L 12 4 L 0 8 L 3 4 Z"
                                            fill="#2563EB"
                                            stroke="#2563EB"
                                            strokeWidth="0.5"
                                            strokeLinejoin="round"
                                        />
                                    </marker>

                                    {/* Фильтр для тени */}
                                    <filter id="drop-shadow" x="-20%" y="-20%" width="140%" height="140%">
                                        <feDropShadow dx="2" dy="2" stdDeviation="3" floodOpacity="0.3"/>
                                    </filter>

                                    {/* Фильтр для свечения соединений */}
                                    <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
                                        <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
                                        <feMerge>
                                            <feMergeNode in="coloredBlur"/>
                                            <feMergeNode in="SourceGraphic"/>
                                        </feMerge>
                                    </filter>
                                </defs>

                                {/* Рёбра */}
                                {currentTrace.edges.map((edge, index) => {
                                    // Создаем изогнутый путь
                                    const midY = edge.fromY + (edge.toY - edge.fromY) / 2;
                                    const controlPoint1Y = edge.fromY + (midY - edge.fromY) * 0.6;
                                    const controlPoint2Y = edge.toY - (edge.toY - midY) * 0.6;

                                    const pathData = `M ${edge.fromX} ${edge.fromY}
                                                     C ${edge.fromX} ${controlPoint1Y},
                                                       ${edge.toX} ${controlPoint2Y},
                                                       ${edge.toX} ${edge.toY}`;

                                    // Проверяем, является ли соединение связанным с session span
                                    const fromNode = currentTrace.nodes.find(n => n.id === edge.from);
                                    const toNode = currentTrace.nodes.find(n => n.id === edge.to);
                                    const isSessionConnection = fromNode?.isSessionSpan || toNode?.isSessionSpan;

                                    return (
                                        <g key={`edge-${index}`} className={styles.connectionGroup}>
                                            {/* Тень соединения */}
                                            <path
                                                d={pathData}
                                                stroke="rgba(0,0,0,0.15)"
                                                strokeWidth="3"
                                                fill="none"
                                                transform="translate(2, 2)"
                                                opacity="0.5"
                                            />

                                            {/* Основное соединение с градиентом */}
                                            <path
                                                d={pathData}
                                                stroke={isSessionConnection ? "url(#sessionConnectionGradient)" : "url(#connectionGradient)"}
                                                strokeWidth={isSessionConnection ? "3" : "2.5"}
                                                fill="none"
                                                markerEnd="url(#arrowhead)"
                                                opacity={isSessionConnection ? "0.95" : "0.85"}
                                                className={`transition-all duration-300 hover:opacity-100 hover:filter hover:drop-shadow-lg ${
                                                    isSessionConnection ? 'hover:stroke-orange-400' : 'hover:stroke-blue-500'
                                                }`}
                                            />

                                            {/* Анимированные точки потока - только на клиенте */}
                                            {isClient && (
                                                <circle
                                                    r={isSessionConnection ? "4" : "3"}
                                                    fill={isSessionConnection ? "#F59E0B" : "#4F46E5"}
                                                    opacity={isSessionConnection ? "0.8" : "0.7"}
                                                    className={styles.flowDot}
                                                >
                                                    <animateMotion
                                                        dur="4s"
                                                        repeatCount="indefinite"
                                                        begin={`${index * 0.3}s`}
                                                    >
                                                        <mpath href={`#path-${index}`} />
                                                    </animateMotion>
                                                </circle>
                                            )}

                                            {/* Скрытый путь для анимации */}
                                            <path
                                                id={`path-${index}`}
                                                d={pathData}
                                                fill="none"
                                                stroke="none"
                                            />
                                        </g>
                                    );
                                })}

                                {/* Узлы */}
                                {currentTrace.nodes.map((node) => (
                                    <g key={node.id}>
                                        {/* Тень узла */}
                                        <rect
                                            x={node.x + 2}
                                            y={node.y + 2}
                                            width={NODE_WIDTH}
                                            height={NODE_HEIGHT}
                                            rx="8"
                                            fill="rgba(0,0,0,0.1)"
                                        />

                                        {/* Основной узел */}
                                        <rect
                                            x={node.x}
                                            y={node.y}
                                            width={NODE_WIDTH}
                                            height={NODE_HEIGHT}
                                            rx="8"
                                            className={`${getNodeStyle(node)} cursor-pointer transition-all duration-200 ${
                                                hoveredNode === node.id ? 'opacity-80 transform-gpu' : ''
                                            }`}
                                            onMouseEnter={() => handleNodeHover(node.id)}
                                            onMouseLeave={() => handleNodeHover(null)}
                                            onClick={() => handleNodeClick(node)}
                                            style={{
                                                transform: hoveredNode === node.id ? 'scale(1.05)' : 'scale(1)',
                                                transformOrigin: 'center'
                                            }}
                                        />

                                        {/* Компактный текст узла */}
                                        <text
                                            x={node.x + NODE_WIDTH / 2}
                                            y={node.y + 16}
                                            textAnchor="middle"
                                            className="fill-white text-xs font-semibold pointer-events-none"
                                        >
                                            {truncateText(node.name, 16)}
                                        </text>

                                        {/* Компактный статус */}
                                        <text
                                            x={node.x + NODE_WIDTH / 2}
                                            y={node.y + 28}
                                            textAnchor="middle"
                                            className="fill-white text-xs opacity-90 pointer-events-none"
                                        >
                                            {node.span.status_code}
                                            {node.isSessionSpan && ' • S'}
                                        </text>

                                        {/* Компактное время */}
                                        <text
                                            x={node.x + NODE_WIDTH / 2}
                                            y={node.y + 38}
                                            textAnchor="middle"
                                            className="fill-white text-xs opacity-75 pointer-events-none"
                                        >
                                            {formatDuration(node.span.start_time, node.span.end_time)}
                                        </text>
                                    </g>
                                ))}

                                {/* Компактный tooltip при наведении */}
                                {hoveredNode && !selectedNode && (
                                    <g>
                                        {(() => {
                                            const node = currentTrace.nodes.find(n => n.id === hoveredNode);
                                            if (!node) return null;

                                            const tooltipX = node.x + NODE_WIDTH + 8;
                                            const tooltipY = node.y;

                                            return (
                                                <g>
                                                    <rect
                                                        x={tooltipX}
                                                        y={tooltipY}
                                                        width="160"
                                                        height="50"
                                                        rx="4"
                                                        fill="rgba(0,0,0,0.9)"
                                                        stroke="#374151"
                                                        strokeWidth="1"
                                                    />
                                                    <text x={tooltipX + 8} y={tooltipY + 16} className="fill-white text-xs font-medium">
                                                        {truncateText(node.name, 18)}
                                                    </text>
                                                    <text x={tooltipX + 8} y={tooltipY + 32} className="fill-gray-300 text-xs">
                                                        Click for details
                                                    </text>
                                                </g>
                                            );
                                        })()}
                                    </g>
                                )}
                            </svg>
                        </div>
                    </div>
                </div>

                {/* Детальная панель - занимает 2/3 высоты когда выбран узел */}
                {selectedNode && (
                    <div className="h-2/3 bg-white overflow-auto">
                        <div className="p-4 h-full">
                            <div className="flex items-center justify-between mb-1 py-1">
                                <div className="flex items-center gap-1">
                                    <div className="p-0.5 bg-blue-100 rounded">
                                        <Activity className="h-3 w-3 text-blue-600" />
                                    </div>
                                    <div>
                                        <h3 className="text-sm font-semibold text-gray-900 leading-tight">
                                            {selectedNode.name.split('.').pop() || selectedNode.name}
                                        </h3>
                                        <p className="text-xs text-gray-600 leading-tight">{selectedNode.name}</p>
                                    </div>
                                </div>
                                <button
                                    onClick={() => setSelectedNode(null)}
                                    className="p-0.5 hover:bg-gray-100 rounded transition-colors"
                                >
                                    <XCircle className="h-3 w-3 text-gray-500" />
                                </button>
                            </div>

                            <div className="flex flex-col h-full gap-2">
                                {/* Максимально сжатая информация о node */}
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
                                                    {new Date(selectedNode.span.start_time).toLocaleTimeString('ru-RU', {
                                                        hour12: false,
                                                        hour: '2-digit',
                                                        minute: '2-digit',
                                                        second: '2-digit'
                                                    })}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    <Timer className="h-3 w-3 text-green-600 mr-1" />
                                                    <div className="text-xs text-gray-600">Duration</div>
                                                </div>
                                                <div className="text-sm font-mono font-bold text-green-700 mt-0.5">
                                                    {formatDuration(selectedNode.span.start_time, selectedNode.span.end_time)}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    {selectedNode.span.status_code === 'OK' ? (
                                                        <CheckCircle className="h-3 w-3 text-green-600 mr-1" />
                                                    ) : selectedNode.span.status_code === 'ERROR' ? (
                                                        <XCircle className="h-3 w-3 text-red-600 mr-1" />
                                                    ) : (
                                                        <AlertTriangle className="h-3 w-3 text-yellow-600 mr-1" />
                                                    )}
                                                    <div className="text-xs text-gray-600">Status</div>
                                                </div>
                                                <div className={`text-xs font-semibold mt-0.5 ${
                                                    selectedNode.span.status_code === 'OK' ? 'text-green-700' :
                                                    selectedNode.span.status_code === 'ERROR' ? 'text-red-700' : 'text-yellow-700'
                                                }`}>
                                                    {selectedNode.span.status_code}
                                                </div>
                                            </div>

                                            <div className="text-center">
                                                <div className="flex items-center justify-center">
                                                    <BarChart3 className="h-3 w-3 text-purple-600 mr-1" />
                                                    <div className="text-xs text-gray-600">Level</div>
                                                </div>
                                                <div className="text-xs font-semibold text-purple-700 mt-0.5">
                                                    L{selectedNode.level}
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Дополнительная информация - одна плоская строка */}
                                    <div className="flex gap-2 text-xs text-gray-600 bg-gray-50 rounded p-1.5">
                                        <span className="flex items-center gap-1">
                                            <Activity className="h-3 w-3" />
                                            <span className="font-medium">Node:</span>
                                            <span className="font-mono truncate max-w-20">{selectedNode.name.split('.').pop() || selectedNode.name}</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <Settings className="h-3 w-3" />
                                            <span className="font-medium">ID:</span>
                                            <span className="font-mono truncate max-w-12">{selectedNode.span.id}</span>
                                        </span>
                                        <span className="flex items-center gap-1">
                                            <Globe className="h-3 w-3" />
                                            <span className="font-medium">{selectedNode.children.length}↓ {selectedNode.parents.length}↑</span>
                                        </span>
                                        {selectedNode.isSessionSpan && (
                                            <span className="px-1 py-0.5 bg-purple-100 text-purple-700 rounded text-xs font-medium">
                                                Session
                                            </span>
                                        )}
                                    </div>
                                </div>

                                {/* Атрибуты - занимают весь доступный контент по высоте */}
                                <div className="flex-1 flex flex-col min-h-0">
                                    {selectedNode.span.attributes && Object.keys(selectedNode.span.attributes).length > 0 ? (
                                        <div className="flex-1 flex flex-col min-h-0">
                                            <div className="flex-shrink-0 mb-0.5">
                                                <label className="block text-xs font-bold text-gray-900 flex items-center gap-1">
                                                    <Settings className="h-3 w-3 text-blue-600" />
                                                    Node Attributes
                                                    <span className="px-1 py-0.5 text-xs bg-blue-100 text-blue-700 rounded font-medium">
                                                        {Object.keys(selectedNode.span.attributes).length}
                                                    </span>
                                                </label>
                                            </div>

                                            <div className="flex-1 bg-gradient-to-br from-gray-50 to-gray-100 rounded border border-gray-200 overflow-hidden min-h-0">
                                                <div className="h-full overflow-auto p-2">
                                                    <div className="space-y-1">
                                                        {Object.entries(selectedNode.span.attributes).map(([key, value]) => {
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
                                                <p className="text-lg font-medium">No attributes available for this node</p>
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
