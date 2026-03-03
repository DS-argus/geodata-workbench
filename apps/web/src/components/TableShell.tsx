import React from "react";

export function formatMb(sizeBytes: number): string {
  return `${(sizeBytes / (1024 * 1024)).toFixed(2)} MB`;
}

type PaginationProps = {
  page: number;
  totalPages: number;
  totalItems: number;
  onPrev: () => void;
  onNext: () => void;
};

export function PaginationRow({ page, totalPages, totalItems, onPrev, onNext }: PaginationProps) {
  return (
    <div className="pager-row">
      <button onClick={onPrev} disabled={page <= 1}>
        ◀ 이전
      </button>
      <span>
        총 {totalItems}건 · {page}/{totalPages} 페이지
      </span>
      <button onClick={onNext} disabled={page >= totalPages}>
        다음 ▶
      </button>
    </div>
  );
}

export type DataTableColumn = {
  key: string;
  title: string;
  width?: string;
  align?: "left" | "center" | "right";
  sortable?: boolean;
  sortKey?: string;
};

type DataTableProps = {
  columns: DataTableColumn[];
  rows: Array<Record<string, React.ReactNode>>;
  emptyText?: string;
  sortBy?: string;
  sortDir?: "asc" | "desc";
  onSortChange?: (sortKey: string) => void;
};

export function DataTable({
  columns,
  rows,
  emptyText = "표시할 항목이 없습니다.",
  sortBy,
  sortDir,
  onSortChange
}: DataTableProps) {
  const shellRef = React.useRef<HTMLDivElement | null>(null);
  const proxyRef = React.useRef<HTMLDivElement | null>(null);
  const syncLockRef = React.useRef(false);
  const [scrollContentWidth, setScrollContentWidth] = React.useState(0);

  const minWidth = columns.reduce((acc, column) => {
    if (!column.width) {
      return acc + 160;
    }
    const numeric = Number(column.width.replace("px", ""));
    return acc + (Number.isFinite(numeric) ? numeric : 160);
  }, 0);

  React.useEffect(() => {
    const updateScrollMetrics = () => {
      const shell = shellRef.current;
      if (!shell) {
        return;
      }
      const table = shell.querySelector("table");
      const width = Math.max(minWidth, table?.scrollWidth ?? 0);
      setScrollContentWidth(width);
      if (proxyRef.current) {
        proxyRef.current.scrollLeft = shell.scrollLeft;
      }
    };
    const frame = window.requestAnimationFrame(updateScrollMetrics);
    window.addEventListener("resize", updateScrollMetrics);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener("resize", updateScrollMetrics);
    };
  }, [minWidth, rows.length, columns.length]);

  return (
    <div className="table-shell-wrap">
      <div
        className="table-shell"
        ref={shellRef}
        onScroll={() => {
          if (!proxyRef.current || syncLockRef.current) {
            return;
          }
          syncLockRef.current = true;
          proxyRef.current.scrollLeft = shellRef.current?.scrollLeft ?? 0;
          window.requestAnimationFrame(() => {
            syncLockRef.current = false;
          });
        }}
      >
        <table className="data-table" style={{ minWidth }}>
          <colgroup>
            {columns.map((column) => (
              <col key={column.key} style={column.width ? { width: column.width } : undefined} />
            ))}
          </colgroup>
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key} style={{ textAlign: column.align ?? "left" }}>
                  {column.sortable && onSortChange ? (
                    <button
                      type="button"
                      className="table-sort-button"
                      onClick={() => onSortChange(column.sortKey ?? column.key)}
                    >
                      <span>{column.title}</span>
                      <span className="table-sort-indicator">
                        {sortBy === (column.sortKey ?? column.key) ? (sortDir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : (
                    column.title
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td className="table-empty" colSpan={columns.length}>
                  {emptyText}
                </td>
              </tr>
            ) : (
              rows.map((row, index) => (
                <tr key={index}>
                  {columns.map((column) => (
                    <td key={column.key} style={{ textAlign: column.align ?? "left" }}>
                      {row[column.key]}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div
        className="table-scrollbar"
        ref={proxyRef}
        onScroll={() => {
          if (!shellRef.current || syncLockRef.current) {
            return;
          }
          syncLockRef.current = true;
          shellRef.current.scrollLeft = proxyRef.current?.scrollLeft ?? 0;
          window.requestAnimationFrame(() => {
            syncLockRef.current = false;
          });
        }}
      >
        <div className="table-scrollbar-inner" style={{ width: `${Math.max(scrollContentWidth, minWidth)}px` }} />
      </div>
    </div>
  );
}
