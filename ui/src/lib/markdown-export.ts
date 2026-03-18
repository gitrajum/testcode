/**
 * Markdown Export Utilities
 * Functions for converting and exporting markdown content to various formats
 */

/**
 * Sanitize filename for safe file download
 */
export function sanitizeFilename(name: string): string {
  // Remove or replace invalid characters
  return name
    .replace(/[^a-z0-9_\-\s]/gi, '_')
    .replace(/\s+/g, '_')
    .replace(/_+/g, '_')
    .substring(0, 100) // Limit length
    || 'export';
}

/**
 * Extract tables from markdown content
 */
function extractTablesFromMarkdown(markdown: string): string[][] {
  const tables: string[][] = [];
  const lines = markdown.split('\n');
  let inTable = false;
  let currentTable: string[][] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    // Check if line is a table row (starts and ends with |)
    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line
        .split('|')
        .slice(1, -1) // Remove first and last empty strings
        .map(cell => cell.trim());

      // Skip separator rows (contain only dashes, colons, and spaces)
      if (!/^[\s\-:]+$/.test(cells.join(''))) {
        currentTable.push(cells);
        inTable = true;
      }
    } else if (inTable) {
      // End of table
      if (currentTable.length > 0) {
        tables.push(...currentTable);
        tables.push([]); // Add blank line between tables
        currentTable = [];
      }
      inTable = false;
    }
  }

  // Add last table if exists
  if (currentTable.length > 0) {
    tables.push(...currentTable);
  }

  return tables;
}

/**
 * Convert markdown to HTML for Word/Excel export
 */
function convertMarkdownToHTML(markdown: string): string {
  let html = markdown;

  // Headers (H1-H6)
  html = html.replace(/^######\s+(.+)$/gm, '<h6>$1</h6>');
  html = html.replace(/^#####\s+(.+)$/gm, '<h5>$1</h5>');
  html = html.replace(/^####\s+(.+)$/gm, '<h4>$1</h4>');
  html = html.replace(/^###\s+(.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^##\s+(.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^#\s+(.+)$/gm, '<h1>$1</h1>');

  // Bold
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/__(.+?)__/g, '<strong>$1</strong>');

  // Italic
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');
  html = html.replace(/_(.+?)_/g, '<em>$1</em>');

  // Code inline
  html = html.replace(/`(.+?)`/g, '<code>$1</code>');

  // Code blocks
  html = html.replace(/```[\s\S]*?```/g, (match) => {
    const code = match.replace(/```\w*\n?/g, '').replace(/```$/g, '');
    return `<pre><code>${code}</code></pre>`;
  });

  // Tables
  const lines = html.split('\n');
  let inTable = false;
  let tableHTML = '';
  const processedLines: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();

    if (line.startsWith('|') && line.endsWith('|')) {
      const cells = line
        .split('|')
        .slice(1, -1)
        .map(cell => cell.trim());

      // Skip separator rows
      if (!/^[\s\-:]+$/.test(cells.join(''))) {
        if (!inTable) {
          tableHTML = '<table border="1" cellpadding="5" cellspacing="0">';
          inTable = true;
        }

        // First row is header
        const tag = processedLines.filter(l => l.includes('<table')).length === 1 && !tableHTML.includes('<tr>') ? 'th' : 'td';
        const rowType = tag === 'th' ? 'thead' : 'tbody';

        if (tag === 'th') {
          tableHTML += '<thead>';
        } else if (!tableHTML.includes('<tbody>')) {
          tableHTML += '<tbody>';
        }

        tableHTML += '<tr>' + cells.map(cell => `<${tag}>${cell}</${tag}>`).join('') + '</tr>';

        if (tag === 'th') {
          tableHTML += '</thead>';
        }
      }
    } else if (inTable) {
      // End of table
      if (tableHTML.includes('<tbody>')) {
        tableHTML += '</tbody>';
      }
      tableHTML += '</table>';
      processedLines.push(tableHTML);
      tableHTML = '';
      inTable = false;
      processedLines.push(line);
    } else {
      processedLines.push(line);
    }
  }

  // Close any remaining table
  if (inTable && tableHTML) {
    if (tableHTML.includes('<tbody>')) {
      tableHTML += '</tbody>';
    }
    tableHTML += '</table>';
    processedLines.push(tableHTML);
  }

  html = processedLines.join('\n');

  // Unordered lists
  html = html.replace(/^\s*[-*+]\s+(.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');

  // Ordered lists
  html = html.replace(/^\s*\d+\.\s+(.+)$/gm, '<li>$1</li>');

  // Links
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');

  // Paragraphs (lines that aren't already HTML)
  html = html.replace(/^(?!<[^>]+>)(.+)$/gm, '<p>$1</p>');

  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');

  return html;
}

/**
 * Export markdown content as CSV
 */
export function exportMarkdownAsCSV(markdown: string, filename: string): void {
  const tables = extractTablesFromMarkdown(markdown);

  let csvContent: string;

  if (tables.length === 0) {
    // No tables found, export as plain text
    csvContent = markdown.replace(/\r?\n/g, '\n');
  } else {
    // Export tables as CSV
    csvContent = tables
      .map(row => {
        if (row.length === 0) return ''; // Blank line between tables
        return row.map(cell => {
          // Escape quotes and wrap in quotes if contains comma, quote, or newline
          const escaped = cell.replace(/"/g, '""');
          return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
        }).join(',');
      })
      .join('\n');
  }

  // Create blob and download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `${filename}.csv`);
}

/**
 * Export markdown content as Excel
 */
export function exportMarkdownAsExcel(markdown: string, filename: string): void {
  const htmlContent = convertMarkdownToHTML(markdown);

  // Create HTML document for Excel
  const excelHTML = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:x="urn:schemas-microsoft-com:office:excel"
          xmlns="http://www.w3.org/TR/REC-html40">
    <head>
      <meta charset="utf-8">
      <style>
        body { font-family: Arial, sans-serif; }
        table { border-collapse: collapse; margin: 10px 0; }
        th { background-color: #4472C4; color: white; font-weight: bold; padding: 8px; border: 1px solid #ccc; }
        td { padding: 8px; border: 1px solid #ccc; }
        h1 { font-size: 24px; color: #2E5090; margin-top: 20px; }
        h2 { font-size: 20px; color: #2E5090; margin-top: 16px; }
        h3 { font-size: 16px; color: #2E5090; margin-top: 12px; }
        code { background-color: #f0f0f0; padding: 2px 4px; font-family: 'Courier New', monospace; }
        pre { background-color: #f0f0f0; padding: 10px; overflow-x: auto; }
      </style>
      <!--[if gte mso 9]>
      <xml>
        <x:ExcelWorkbook>
          <x:ExcelWorksheets>
            <x:ExcelWorksheet>
              <x:Name>Export</x:Name>
              <x:WorksheetOptions>
                <x:DisplayGridlines/>
              </x:WorksheetOptions>
            </x:ExcelWorksheet>
          </x:ExcelWorksheets>
        </x:ExcelWorkbook>
      </xml>
      <![endif]-->
    </head>
    <body>
      ${htmlContent}
    </body>
    </html>
  `;

  // Create blob and download
  const blob = new Blob([excelHTML], { type: 'application/vnd.ms-excel' });
  downloadBlob(blob, `${filename}.xls`);
}

/**
 * Export markdown content as Word document
 */
export function exportMarkdownAsWord(markdown: string, filename: string): void {
  const htmlContent = convertMarkdownToHTML(markdown);

  // Create HTML document for Word
  const wordHTML = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office"
          xmlns:w="urn:schemas-microsoft-com:office:word"
          xmlns="http://www.w3.org/TR/REC-html40">
    <head>
      <meta charset="utf-8">
      <style>
        body {
          font-family: 'Calibri', Arial, sans-serif;
          font-size: 11pt;
          line-height: 1.6;
          margin: 1in;
        }
        table {
          border-collapse: collapse;
          margin: 10px 0;
          width: 100%;
        }
        th {
          background-color: #4472C4;
          color: white;
          font-weight: bold;
          padding: 8px;
          border: 1px solid #333;
          text-align: left;
        }
        td {
          padding: 8px;
          border: 1px solid #333;
        }
        h1 {
          font-size: 24pt;
          color: #2E5090;
          margin-top: 24pt;
          margin-bottom: 12pt;
          page-break-after: avoid;
        }
        h2 {
          font-size: 18pt;
          color: #2E5090;
          margin-top: 18pt;
          margin-bottom: 10pt;
          page-break-after: avoid;
        }
        h3 {
          font-size: 14pt;
          color: #2E5090;
          margin-top: 14pt;
          margin-bottom: 8pt;
          page-break-after: avoid;
        }
        h4, h5, h6 {
          color: #2E5090;
          page-break-after: avoid;
        }
        code {
          background-color: #f0f0f0;
          padding: 2px 4px;
          font-family: 'Courier New', monospace;
          font-size: 10pt;
        }
        pre {
          background-color: #f0f0f0;
          padding: 10px;
          overflow-x: auto;
          border: 1px solid #ccc;
          page-break-inside: avoid;
        }
        pre code {
          background-color: transparent;
          padding: 0;
        }
        ul, ol {
          margin: 10px 0;
          padding-left: 30px;
        }
        li {
          margin: 5px 0;
        }
        p {
          margin: 10px 0;
        }
        a {
          color: #0563C1;
          text-decoration: underline;
        }
      </style>
    </head>
    <body>
      ${htmlContent}
    </body>
    </html>
  `;

  // Create blob and download
  const blob = new Blob([wordHTML], { type: 'application/msword' });
  downloadBlob(blob, `${filename}.doc`);
}

/**
 * Helper function to trigger download of a blob
 */
function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.style.display = 'none';

  document.body.appendChild(link);
  link.click();

  // Cleanup
  setTimeout(() => {
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }, 100);
}
