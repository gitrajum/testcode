import React, { useState, useRef, useCallback } from "react";
import { TraceNode } from "@/hooks/useTrace";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AlertTriangle, Activity, GripVertical, RefreshCw, GitBranch, BarChart3 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { TraceGraph } from "./TraceGraph";
import { JaegerTraceView } from "./JaegerTraceView";

interface TraceSidebarProps {
    trace: TraceNode[] | null;
    loading: boolean;
    error: string | null;
    projectId?: string | null;
    availableProjects?: Array<{id: string; name: string; description?: string}>;
    refreshTrace?: () => void;
    contextId?: string;
}

export const TraceSidebar: React.FC<TraceSidebarProps> = ({ trace, loading, error, projectId, availableProjects = [], refreshTrace, contextId }) => {
    const [width, setWidth] = useState(() => {
        // Загружаем сохраненную ширину из localStorage
        if (typeof window !== 'undefined') {
            const savedWidth = localStorage.getItem('phoenix-sidebar-width');
            return savedWidth ? parseInt(savedWidth, 10) : 320;
        }
        return 320;
    });
    const [isResizing, setIsResizing] = useState(false);
    const [viewMode, setViewMode] = useState<'graph' | 'jaeger'>('jaeger');
    const sidebarRef = useRef<HTMLDivElement>(null);

    const startResize = useCallback((e: React.MouseEvent) => {
        setIsResizing(true);
        e.preventDefault();
    }, []);

    const stopResize = useCallback(() => {
        setIsResizing(false);
    }, []);

    const resize = useCallback((e: MouseEvent) => {
        if (isResizing && sidebarRef.current) {
            const rect = sidebarRef.current.getBoundingClientRect();
            const newWidth = e.clientX - rect.left;

            // Ограничиваем ширину от 200px до 800px (увеличил для Jaeger view)
            const clampedWidth = Math.min(Math.max(newWidth, 200), 800);
            setWidth(clampedWidth);

            // Сохраняем ширину в localStorage
            if (typeof window !== 'undefined') {
                localStorage.setItem('phoenix-sidebar-width', clampedWidth.toString());
            }
        }
    }, [isResizing]);

    React.useEffect(() => {
        if (isResizing) {
            document.addEventListener('mousemove', resize);
            document.addEventListener('mouseup', stopResize);
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        } else {
            document.removeEventListener('mousemove', resize);
            document.removeEventListener('mouseup', stopResize);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        }

        return () => {
            document.removeEventListener('mousemove', resize);
            document.removeEventListener('mouseup', stopResize);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
    }, [isResizing, resize, stopResize]);



    return (
        <div
            ref={sidebarRef}
            className="relative border-r bg-background overflow-hidden flex h-full"
            style={{ width: `${width}px` }}
        >
            {/* Основное содержимое */}
            <div className="flex-1 flex flex-col overflow-hidden">
                {/* Заголовок - фиксированная высота */}
                <div className="flex-shrink-0 p-4 border-b border-border">
                    <div className="flex items-center justify-between mb-2">
                        <h3 className="text-lg font-semibold text-foreground flex items-center gap-2">
                            <Activity className="h-5 w-5" />
                            Phoenix Trace
                            <span className="text-xs text-muted-foreground font-normal">
                                ({width}px)
                            </span>
                        </h3>
                        <div className="flex items-center gap-1">
                            {/* View Mode Toggle */}
                            <div className="flex items-center border rounded-md">
                                <Button
                                    variant={viewMode === 'jaeger' ? 'default' : 'ghost'}
                                    size="sm"
                                    onClick={() => setViewMode('jaeger')}
                                    className="h-7 px-2 rounded-r-none border-r"
                                    title="Jaeger timeline view"
                                >
                                    <BarChart3 className="h-3 w-3" />
                                </Button>
                                <Button
                                    variant={viewMode === 'graph' ? 'default' : 'ghost'}
                                    size="sm"
                                    onClick={() => setViewMode('graph')}
                                    className="h-7 px-2 rounded-l-none"
                                    title="Graph view"
                                >
                                    <GitBranch className="h-3 w-3" />
                                </Button>
                            </div>

                            {/* Refresh Button */}
                            {refreshTrace && (
                                <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={refreshTrace}
                                    disabled={loading}
                                    className="h-7 w-7 p-0"
                                    title="Refresh traces"
                                >
                                    <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
                                </Button>
                            )}
                        </div>
                    </div>

                    {/* Project ID */}
                    {projectId && (
                        <div className="text-xs text-muted-foreground mb-2 p-2 bg-muted/50 rounded-md">
                            <div className="font-medium">Project ID:</div>
                            <div className="font-mono">{projectId}</div>
                        </div>
                    )}

                    {/* Status messages */}
                    {loading && (
                        <div className="text-sm text-muted-foreground flex items-center gap-2">
                            <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-primary"></div>
                            Loading trace...
                        </div>
                    )}
                    {error && (
                        <div className="text-sm p-3 border rounded-md">
                            {error.includes('Проект не найден') ? (
                                <div className="space-y-2">
                                    <div className="flex items-center gap-2 text-amber-600">
                                        <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                                        <span className="font-medium">Проект не найден</span>
                                    </div>
                                    <div className="text-sm text-muted-foreground">
                                        {error}
                                    </div>
                                    <div className="text-xs text-muted-foreground p-2 bg-muted/50 rounded border-l-2 border-amber-300">
                                        <strong>Совет:</strong> Убедитесь, что в Phoenix существует проект с именем,
                                        соответствующим имени выбранного агента, или выберите другого агента.
                                    </div>
                                    {availableProjects.length > 0 && (
                                        <div className="mt-2 p-2 bg-blue-50 dark:bg-blue-950/20 rounded border border-blue-200 dark:border-blue-800">
                                            <div className="text-xs font-medium text-blue-800 dark:text-blue-200 mb-1">
                                                Доступные проекты в Phoenix:
                                            </div>
                                            <div className="space-y-1">
                                                {availableProjects.map(project => (
                                                    <div key={project.id} className="text-xs font-mono text-blue-700 dark:text-blue-300 bg-blue-100 dark:bg-blue-900/30 px-2 py-1 rounded">
                                                        {project.name}
                                                        {project.description && (
                                                            <span className="text-blue-600 dark:text-blue-400 ml-1">
                                                                - {project.description}
                                                            </span>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 text-destructive">
                                    <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                                    <span>{error}</span>
                                </div>
                            )}
                        </div>
                    )}
                    {!loading && !error && (!trace || trace.length === 0) && (
                        <p className="text-sm text-muted-foreground">No spans found</p>
                    )}
                </div>

                {/* Контент - занимает оставшуюся высоту */}
                {trace && trace.length > 0 && (
                    <div className="flex-1 overflow-hidden">
                        {viewMode === 'jaeger' ? (
                            <JaegerTraceView trace={trace} contextId={contextId} />
                        ) : (
                            <ScrollArea className="h-full">
                                <TraceGraph trace={trace} contextId={contextId} />
                            </ScrollArea>
                        )}
                    </div>
                )}
            </div>

            {/* Разделитель для изменения размера */}
            <div
                className={`w-1 bg-border hover:bg-primary/50 cursor-col-resize flex items-center justify-center transition-colors ${
                    isResizing ? 'bg-primary/50' : ''
                }`}
                onMouseDown={startResize}
                title="Drag to resize Phoenix panel"
            >
                <GripVertical className="h-4 w-4 text-muted-foreground" />
            </div>
        </div>
    );
};
