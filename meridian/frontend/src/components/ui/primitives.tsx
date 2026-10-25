import type { ReactNode } from "react";

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />;
}

export function EmptyState({
  icon, title, hint, action,
}: { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      {icon && <div className="text-fg-3">{icon}</div>}
      <div className="text-[13px] font-medium text-fg-2">{title}</div>
      {hint && <div className="text-[11px] text-fg-3">{hint}</div>}
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Something went wrong", hint, requestId, onRetry,
}: { title?: string; hint?: string; requestId?: string; onRetry?: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
      <div className="text-[13px] font-medium text-down">{title}</div>
      {hint && <div className="text-[11px] text-fg-3">{hint}</div>}
      <div className="flex items-center gap-3">
        {onRetry && (
          <button onClick={onRetry} className="rounded bg-elevated px-2.5 py-1 text-[11px] text-fg hover:bg-hairline">
            Retry
          </button>
        )}
        {requestId && (
          <button
            className="text-[10px] text-fg-3 underline decoration-dotted"
            onClick={() => navigator.clipboard.writeText(requestId)}
            title="Copy correlation id for support"
          >
            ref {requestId}
          </button>
        )}
      </div>
    </div>
  );
}

export function Chip({ children, tone = "neutral", onRemove }: {
  children: ReactNode;
  tone?: "neutral" | "accent" | "genie" | "up" | "down" | "warn";
  onRemove?: () => void;
}) {
  const tones: Record<string, string> = {
    neutral: "bg-elevated text-fg-2 border-hairline",
    accent: "bg-accent/15 text-accent border-accent/40",
    genie: "bg-genie/15 text-genie border-genie/40",
    up: "bg-up/15 text-up border-up/40",
    down: "bg-down/15 text-down border-down/40",
    warn: "bg-warn/15 text-warn border-warn/40",
  };
  return (
    <span className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] ${tones[tone]}`}>
      {children}
      {onRemove && (
        <button onClick={onRemove} className="opacity-60 hover:opacity-100" aria-label="remove">
          ×
        </button>
      )}
    </span>
  );
}
