interface SkeletonProps {
  className?: string;
  /** Announced to assistive technology while content is loading. */
  label?: string;
}

/**
 * A themed placeholder block. The shimmer and both surface colours come from
 * `.jm-skeleton` in index.css, so it is legible on either ground and honours
 * `prefers-reduced-motion`.
 */
export function Skeleton({ className = 'h-4 w-full', label }: SkeletonProps) {
  return (
    <div
      className={`jm-skeleton ${className}`.trim()}
      role={label ? 'status' : 'presentation'}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
}

/** The shape of a trip card, used while history is loading. */
export function SkeletonCard() {
  return (
    <div className="rounded-2xl border border-line bg-surface p-4 shadow-card">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="mt-3 h-3 w-2/3" />
      <div className="mt-4 flex gap-2">
        <Skeleton className="h-8 w-20 rounded-lg" />
        <Skeleton className="h-8 w-20 rounded-lg" />
      </div>
    </div>
  );
}
