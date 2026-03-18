import React, { useRef, useEffect, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';
import { CodeBlock } from './CodeBlock';
import { ExportTableButton } from './ExportTableButton';

interface MarkdownRendererProps {
    content: string;
    className?: string;
    compact?: boolean;
}

// Separate component for tables to properly use React hooks
const TableComponent: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const tableRef = useRef<HTMLTableElement>(null);
    const [tableName, setTableName] = useState<string>('');

    useEffect(() => {
        // Find the table heading from previous siblings when component mounts
        if (tableRef.current) {
            let current = tableRef.current.parentElement?.previousElementSibling;
            while (current) {
                const tagName = current.tagName?.toLowerCase();
                if (tagName && ['h1', 'h2', 'h3', 'h4', 'h5', 'h6'].includes(tagName)) {
                    setTableName(current.textContent?.trim() || '');
                    break;
                }
                current = current.previousElementSibling;
            }
        }
    }, []);

    return (
        <div className="my-4">
            <div className="flex items-center justify-between mb-2 px-2 py-1 bg-muted/30 rounded-t-md border-x border-t border-border">
                <div className="text-xs text-muted-foreground">
                    {tableName && <span className="font-medium">{tableName}</span>}
                </div>
                <ExportTableButton tableRef={tableRef} tableName={tableName} />
            </div>
            <div className="overflow-x-auto border border-border rounded-b-md">
                <table ref={tableRef} className="w-full border-collapse">
                    {children}
                </table>
            </div>
        </div>
    );
};

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content, className = '', compact = false }) => {
    const components: Components = {
        // Headers with custom styling
        h1: ({ children }) => (
            <h1 className={compact ? "text-2xl font-bold mt-3 mb-2 text-foreground" : "text-3xl font-bold mt-6 mb-4 text-foreground border-b border-border pb-2"}>
                {children}
            </h1>
        ),
        h2: ({ children }) => (
            <h2 className={compact ? "text-xl font-bold mt-2 mb-1.5 text-foreground" : "text-2xl font-bold mt-5 mb-3 text-foreground border-b border-border pb-2"}>
                {children}
            </h2>
        ),
        h3: ({ children }) => (
            <h3 className={compact ? "text-lg font-semibold mt-2 mb-1 text-foreground" : "text-xl font-semibold mt-4 mb-2 text-foreground"}>
                {children}
            </h3>
        ),
        h4: ({ children }) => (
            <h4 className={compact ? "text-base font-semibold mt-1.5 mb-1 text-foreground" : "text-lg font-semibold mt-3 mb-2 text-foreground"}>
                {children}
            </h4>
        ),
        h5: ({ children }) => (
            <h5 className={compact ? "text-sm font-semibold mt-1 mb-0.5 text-foreground" : "text-base font-semibold mt-2 mb-1 text-foreground"}>
                {children}
            </h5>
        ),
        h6: ({ children }) => (
            <h6 className={compact ? "text-sm font-semibold mt-1 mb-0.5 text-muted-foreground" : "text-sm font-semibold mt-2 mb-1 text-muted-foreground"}>
                {children}
            </h6>
        ),

        // Paragraphs
        p: ({ children }) => (
            <p className={compact ? "mb-2 leading-6 text-foreground" : "mb-4 leading-7 text-foreground"}>
                {children}
            </p>
        ),

        // Links
        a: ({ href, children }) => (
            <a
                href={href}
                className="text-primary hover:text-primary/80 underline underline-offset-4"
                target="_blank"
                rel="noopener noreferrer"
            >
                {children}
            </a>
        ),

        // Code blocks
        code: ({ node, className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const isInline = !match;
            const language = match ? match[1] : '';

            if (isInline) {
                return (
                    <code
                        className="relative rounded bg-muted px-[0.3rem] py-[0.2rem] font-mono text-sm text-foreground"
                    >
                        {children}
                    </code>
                );
            }

            const code = String(children).replace(/\n$/, '');

            if (language) {
                return <CodeBlock language={language} code={code} compact={compact} />;
            }

            return (
                <pre className={compact ? "mb-2 mt-1 overflow-x-auto rounded-lg border border-border bg-muted p-3" : "mb-4 mt-2 overflow-x-auto rounded-lg border border-border bg-muted p-4"}>
                    <code className={`font-mono text-sm text-foreground ${className || ''}`}>
                        {children}
                    </code>
                </pre>
            );
        },

        // Pre (wraps code blocks)
        pre: ({ children }) => <>{children}</>,

        // Lists
        ul: ({ children }) => (
            <ul className={compact ? "my-2 ml-4 list-disc space-y-1 text-foreground" : "my-4 ml-6 list-disc space-y-2 text-foreground"}>
                {children}
            </ul>
        ),
        ol: ({ children }) => (
            <ol className={compact ? "my-2 ml-4 list-decimal space-y-1 text-foreground" : "my-4 ml-6 list-decimal space-y-2 text-foreground"}>
                {children}
            </ol>
        ),
        li: ({ children }) => (
            <li className="leading-7">
                {children}
            </li>
        ),

        // Blockquotes
        blockquote: ({ children }) => (
            <blockquote className="mt-4 border-l-4 border-primary/50 pl-4 italic text-muted-foreground">
                {children}
            </blockquote>
        ),

        // Tables - wrapped with export functionality
        table: ({ children }) => (
            <TableComponent>
                {children}
            </TableComponent>
        ),
        thead: ({ children }) => (
            <thead className="bg-muted">
                {children}
            </thead>
        ),
        tbody: ({ children }) => (
            <tbody>
                {children}
            </tbody>
        ),
        tr: ({ children }) => (
            <tr className="border-b border-border">
                {children}
            </tr>
        ),
        th: ({ children }) => (
            <th className="px-4 py-2 text-left font-semibold text-foreground">
                {children}
            </th>
        ),
        td: ({ children }) => (
            <td className="px-4 py-2 text-foreground">
                {children}
            </td>
        ),

        // Horizontal rule
        hr: () => (
            <hr className="my-6 border-t border-border" />
        ),

        // Strong/Bold
        strong: ({ children }) => (
            <strong className="font-bold text-foreground">
                {children}
            </strong>
        ),

        // Emphasis/Italic
        em: ({ children }) => (
            <em className="italic">
                {children}
            </em>
        ),

        // Strikethrough (requires remark-gfm)
        del: ({ children }) => (
            <del className="line-through text-muted-foreground">
                {children}
            </del>
        ),

        // Task lists (requires remark-gfm)
        input: ({ type, checked, disabled }) => {
            if (type === 'checkbox') {
                return (
                    <input
                        type="checkbox"
                        checked={checked}
                        disabled={disabled}
                        className="mr-2 align-middle"
                        readOnly
                    />
                );
            }
            return <input type={type} />;
        },
    };

    return (
        <div className={`markdown-content ${className}`}>
            <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={components}
            >
                {content}
            </ReactMarkdown>
        </div>
    );
};
