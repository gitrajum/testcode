/**
 * Table Export Utilities
 * Functions for extracting and exporting table data to CSV and Excel formats
 */

/**
 * Extract table data from HTML table element
 */
export function extractTableDataFromHTML(table: HTMLTableElement): string[][] {
  const data: string[][] = [];

  // Extract headers
  const headers: string[] = [];
  const headerCells = table.querySelectorAll('thead th, thead td');
  headerCells.forEach(cell => {
    headers.push(cell.textContent?.trim() || '');
  });

  if (headers.length > 0) {
    data.push(headers);
  }

  // Extract body rows
  const rows = table.querySelectorAll('tbody tr');
  rows.forEach(row => {
    const rowData: string[] = [];
    const cells = row.querySelectorAll('td, th');
    cells.forEach(cell => {
      rowData.push(cell.textContent?.trim() || '');
    });
    if (rowData.length > 0) {
      data.push(rowData);
    }
  });

  return data;
}

/**
 * Export table data to CSV format
 */
export function exportToCSV(data: string[][], filename: string): void {
  // Convert data to CSV format
  const csvContent = data
    .map(row =>
      row.map(cell => {
        // Escape quotes and wrap in quotes if contains comma, quote, or newline
        const escaped = cell.replace(/"/g, '""');
        return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
      }).join(',')
    )
    .join('\n');

  // Create blob and download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  downloadBlob(blob, `${filename}.csv`);
}

/**
 * Export table data to Excel format (using basic HTML table method)
 */
export function exportToExcel(data: string[][], filename: string, sheetName: string = 'Sheet1'): void {
  // Create HTML table
  const htmlTable = `
    <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:x="urn:schemas-microsoft-com:office:excel" xmlns="http://www.w3.org/TR/REC-html40">
    <head>
      <meta charset="utf-8">
      <!--[if gte mso 9]>
      <xml>
        <x:ExcelWorkbook>
          <x:ExcelWorksheets>
            <x:ExcelWorksheet>
              <x:Name>${sheetName}</x:Name>
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
      <table>
        ${data.map((row, idx) => `
          <tr>
            ${row.map(cell => {
              const tag = idx === 0 ? 'th' : 'td';
              const escaped = cell.replace(/</g, '&lt;').replace(/>/g, '&gt;');
              return `<${tag}>${escaped}</${tag}>`;
            }).join('')}
          </tr>
        `).join('')}
      </table>
    </body>
    </html>
  `;

  // Create blob and download
  const blob = new Blob([htmlTable], { type: 'application/vnd.ms-excel' });
  downloadBlob(blob, `${filename}.xls`);
}

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
    || 'table_export';
}

/**
 * Find context/name for the table based on nearby headings or aria-label
 */
export function findTableContext(table: HTMLTableElement): string {
  // Check for aria-label
  const ariaLabel = table.getAttribute('aria-label');
  if (ariaLabel) return ariaLabel;

  // Check for caption
  const caption = table.querySelector('caption');
  if (caption?.textContent) return caption.textContent.trim();

  // Look for preceding heading
  let element = table.previousElementSibling;
  while (element) {
    if (/^H[1-6]$/.test(element.tagName)) {
      return element.textContent?.trim() || '';
    }
    element = element.previousElementSibling;
  }

  // Default name
  return 'table_data';
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
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
