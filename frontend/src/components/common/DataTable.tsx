import type { ReactNode } from 'react';

export interface Column<T> {
  key: string;
  header: string;
  render?: (row: T) => ReactNode;
}

export function DataTable<T>({
  columns,
  data,
}: {
  columns: Column<T>[];
  data: T[];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] bg-[var(--color-bg-secondary)]">
            {columns.map((col) => (
              <th key={col.key} className="px-4 py-3 text-left font-medium text-[var(--color-text-secondary)]">
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr
              key={i}
              className="border-b border-[var(--color-border)] last:border-0 hover:bg-white/5"
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3">
                  {col.render
                    ? col.render(row)
                    : String((row as Record<string, unknown>)[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
          {data.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-[var(--color-text-secondary)]">
                No data
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
