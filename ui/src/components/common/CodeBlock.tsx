import React, { useState } from 'react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus, vs } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { Copy, Check } from 'lucide-react';

interface CodeBlockProps {
    language: string;
    code: string;
    compact?: boolean;
}

export const CodeBlock: React.FC<CodeBlockProps> = ({ language, code, compact = false }) => {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        try {
            await navigator.clipboard.writeText(code);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        } catch (err) {
            console.error('Failed to copy code:', err);
        }
    };

    // Get theme from document root's class
    const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
    const codeStyle = isDark ? vscDarkPlus : vs;

    return (
        <div className={`relative group ${compact ? "mb-2 mt-1" : "mb-4 mt-2"}`}>
            {/* Language label and copy button */}
            <div className="flex items-center justify-between px-4 py-2 bg-muted/50 border-b border-border rounded-t-lg">
                <span className="text-xs font-mono text-muted-foreground uppercase">
                    {language}
                </span>
                <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 px-2 py-1 text-xs rounded hover:bg-muted transition-colors"
                    aria-label="Copy code"
                >
                    {copied ? (
                        <>
                            <Check className="h-3.5 w-3.5 text-green-500" />
                            <span className="text-green-500">Copied!</span>
                        </>
                    ) : (
                        <>
                            <Copy className="h-3.5 w-3.5" />
                            <span>Copy</span>
                        </>
                    )}
                </button>
            </div>

            {/* Code content with syntax highlighting */}
            <SyntaxHighlighter
                language={language}
                style={codeStyle as any}
                customStyle={{
                    margin: 0,
                    borderTopLeftRadius: 0,
                    borderTopRightRadius: 0,
                    borderBottomLeftRadius: '0.5rem',
                    borderBottomRightRadius: '0.5rem',
                    fontSize: '0.875rem',
                    padding: compact ? '0.75rem' : '1rem',
                }}
                showLineNumbers={!compact && code.split('\n').length > 5}
                wrapLines={true}
            >
                {code}
            </SyntaxHighlighter>
        </div>
    );
};
