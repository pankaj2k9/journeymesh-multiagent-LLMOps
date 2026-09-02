interface SpinnerProps {
  label: string;
  className?: string;
}

export function Spinner({ label, className = '' }: SpinnerProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`flex items-center justify-center gap-3 py-10 text-journey-slate ${className}`.trim()}
    >
      <span className="h-5 w-5 animate-spin rounded-full border-2 border-mesh-500 border-t-transparent" />
      <span className="text-sm">{label}</span>
    </div>
  );
}
