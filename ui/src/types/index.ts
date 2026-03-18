// Re-export all types from specific modules
export * from './chat';

// Common utility types
export interface ApiResponse<T = any> {
  data?: T;
  error?: string;
  success: boolean;
  timestamp: string;
}

export interface PaginatedResponse<T> extends ApiResponse<T[]> {
  pagination: {
    page: number;
    limit: number;
    total: number;
    totalPages: number;
  };
}

// Error types
export interface AppError {
  code: string;
  message: string;
  details?: Record<string, any>;
  timestamp: string;
}

// Loading states
export type LoadingState = 'idle' | 'loading' | 'success' | 'error';

// Theme types
export type ThemeMode = 'light' | 'dark' | 'system';

// Navigation types
export type TabType = 'chats' | 'agents' | 'chat';

// Component props types
export interface BaseComponentProps {
  className?: string;
  children?: React.ReactNode;
}

// Phoenix tracing types
export interface PhoenixProject {
  id: string;
  name: string;
  description?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface SpanAttribute {
  [key: string]: string | number | boolean | null;
}

export interface SpanEvent {
  name: string;
  timestamp: string;
  attributes: SpanAttribute;
}

export interface TraceSpan {
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
  attributes: SpanAttribute;
  events: SpanEvent[];
}

// Storage utilities types
export interface StorageConfig {
  key: string;
  defaultValue: any;
  serialize?: (value: any) => string;
  deserialize?: (value: string) => any;
}
