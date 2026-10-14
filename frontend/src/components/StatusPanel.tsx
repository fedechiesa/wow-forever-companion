import type { ReactNode } from "react";

export function StatusPanel({ title, children, error = false, loading = false, onRetry }: {
  title: string; children?: ReactNode; error?: boolean; loading?: boolean; onRetry?: () => void;
}) {
  return <div className={`status-panel ${error ? "status-error" : ""}`} role={error ? "alert" : "status"}>
    <span className={loading ? "status-symbol spinner" : "status-symbol"} aria-hidden="true">{loading ? "" : error ? "!" : "◇"}</span>
    <h3>{title}</h3>{children && <p>{children}</p>}
    {onRetry && <button className="button-secondary" onClick={onRetry}>Reintentar</button>}
  </div>;
}
