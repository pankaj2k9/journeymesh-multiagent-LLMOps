import type { ReactNode } from 'react';

type Tone = 'info' | 'warning' | 'danger' | 'success';

const TONES: Record<Tone, string> = {
  info: 'border-sky-200 bg-sky-50 text-sky-900',
  warning: 'border-amber-200 bg-amber-50 text-amber-900',
  danger: 'border-rose-200 bg-rose-50 text-rose-900',
  success: 'border-emerald-200 bg-emerald-50 text-emerald-900',
};

interface CalloutProps {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function Callout({ tone = 'info', title, children, actions }: CalloutProps) {
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${TONES[tone]}`} role="status">
      {title ? <p className="font-semibold">{title}</p> : null}
      <div className={title ? 'mt-1' : undefined}>{children}</div>
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
