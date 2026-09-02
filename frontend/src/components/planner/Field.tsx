import type { ReactNode } from 'react';

interface FieldProps {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string;
  optional?: string;
  children: ReactNode;
  className?: string;
}

export function Field({
  label,
  htmlFor,
  hint,
  error,
  optional,
  children,
  className = '',
}: FieldProps) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="block text-sm font-medium text-journey-ink">
        {label}
        {optional ? (
          <span className="ml-1 text-xs font-normal text-journey-slate">({optional})</span>
        ) : null}
      </label>
      <div className="mt-1.5">{children}</div>
      {hint && !error ? <p className="mt-1 text-xs text-journey-slate">{hint}</p> : null}
      {error ? (
        <p className="mt-1 text-xs text-rose-700" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  'w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-journey-ink placeholder:text-slate-400 focus:border-mesh-500 focus:outline-none focus:ring-2 focus:ring-mesh-200';
