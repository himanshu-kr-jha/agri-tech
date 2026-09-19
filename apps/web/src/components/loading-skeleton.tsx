/**
 * Skeleton fallback for the chat panel's Suspense boundary — replaces a bare "Loading…"
 * paragraph, which reads as a broken app on a slow connection rather than a working one.
 */

export function ChatSkeleton({ label }: { label: string }) {
  return (
    <div role="status" className="space-y-3">
      <span className="sr-only">{label}</span>
      <div aria-hidden="true" className="panel animate-pulse space-y-3">
        <div className="h-3 w-1/3 rounded bg-muted" />
        <div className="h-3 w-full rounded bg-muted" />
        <div className="h-3 w-5/6 rounded bg-muted" />
      </div>
      <div aria-hidden="true" className="h-11 w-full animate-pulse rounded-md bg-muted" />
    </div>
  );
}
