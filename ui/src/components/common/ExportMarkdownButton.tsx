import React, { useState } from 'react';
import { Download, FileText, FileSpreadsheet, FileType } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  exportMarkdownAsCSV,
  exportMarkdownAsExcel,
  exportMarkdownAsWord,
  sanitizeFilename,
} from '@/lib/markdown-export';

interface ExportMarkdownButtonProps {
  markdown: string;
  filename?: string;
  variant?: 'default' | 'outline' | 'ghost';
  size?: 'default' | 'sm' | 'lg' | 'icon';
  className?: string;
}

export const ExportMarkdownButton: React.FC<ExportMarkdownButtonProps> = ({
  markdown,
  filename = 'export',
  variant = 'outline',
  size = 'sm',
  className = '',
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleExport = (format: 'csv' | 'excel' | 'word') => {
    const sanitizedFilename = sanitizeFilename(filename);

    try {
      switch (format) {
        case 'csv':
          exportMarkdownAsCSV(markdown, sanitizedFilename);
          break;
        case 'excel':
          exportMarkdownAsExcel(markdown, sanitizedFilename);
          break;
        case 'word':
          exportMarkdownAsWord(markdown, sanitizedFilename);
          break;
      }
      setIsOpen(false);
    } catch (error) {
      console.error('Export failed:', error);
      alert('Failed to export document. Please try again.');
    }
  };

  return (
    <div className="relative inline-block">
      <Button
        variant={variant}
        size={size}
        className={`${className}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <Download className="h-4 w-4 mr-2" />
        Export Document
      </Button>

      {isOpen && (
        <>
          {/* Backdrop to close dropdown */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown menu */}
          <div className="absolute right-0 mt-1 w-48 rounded-md shadow-lg bg-popover border border-border z-20">
            <div className="py-1" role="menu">
              <button
                className="flex items-center w-full px-4 py-2 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => handleExport('csv')}
                role="menuitem"
              >
                <FileText className="h-4 w-4 mr-2" />
                Export as CSV
              </button>
              <button
                className="flex items-center w-full px-4 py-2 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => handleExport('excel')}
                role="menuitem"
              >
                <FileSpreadsheet className="h-4 w-4 mr-2" />
                Export as Excel
              </button>
              <button
                className="flex items-center w-full px-4 py-2 text-sm text-foreground hover:bg-accent hover:text-accent-foreground"
                onClick={() => handleExport('word')}
                role="menuitem"
              >
                <FileType className="h-4 w-4 mr-2" />
                Export as Word
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
};
