import React, { useState } from 'react';
import { Download, FileSpreadsheet, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  extractTableDataFromHTML,
  exportToCSV,
  exportToExcel,
  sanitizeFilename,
  findTableContext,
} from '@/lib/table-export';

interface ExportTableButtonProps {
  tableRef: React.RefObject<HTMLTableElement | null>;
  tableName?: string;
}

export const ExportTableButton: React.FC<ExportTableButtonProps> = ({
  tableRef,
  tableName
}) => {
  const [isOpen, setIsOpen] = useState(false);

  const handleExport = (format: 'csv' | 'excel') => {
    if (!tableRef.current) {
      console.error('Table reference not available');
      return;
    }

    try {
      // Extract table data
      const data = extractTableDataFromHTML(tableRef.current);

      if (data.length === 0) {
        alert('No data to export');
        return;
      }

      // Determine filename
      const context = tableName || findTableContext(tableRef.current);
      const filename = sanitizeFilename(context);

      // Export based on format
      if (format === 'csv') {
        exportToCSV(data, filename);
      } else {
        exportToExcel(data, filename, context);
      }

      setIsOpen(false);
    } catch (error) {
      console.error('Export failed:', error);
      alert('Failed to export table. Please try again.');
    }
  };

  return (
    <div className="relative inline-block">
      <Button
        variant="outline"
        size="sm"
        className="h-7 px-3 text-xs font-medium"
        onClick={() => setIsOpen(!isOpen)}
      >
        <Download className="h-3.5 w-3.5 mr-1.5" />
        Export
      </Button>

      {isOpen && (
        <>
          {/* Backdrop to close dropdown */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Dropdown menu */}
          <div className="absolute right-0 mt-1 w-40 rounded-md shadow-lg bg-popover border border-border z-20">
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
            </div>
          </div>
        </>
      )}
    </div>
  );
};
