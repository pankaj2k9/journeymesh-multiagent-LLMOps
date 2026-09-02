import type { ReactNode } from 'react';

export type BadgeTone = 'positive' | 'neutral' | 'caution' | 'negative' | 'muted' | 'brand';

const TONES: Record<BadgeTone, string> = {
  positive: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
  neutral: 'bg-sky-50 text-sky-700 ring-sky-200',
  caution: 'bg-amber-50 text-amber-800 ring-amber-200',
  negative: 'bg-rose-50 text-rose-700 ring-rose-200',
  muted: 'bg-slate-100 text-slate-600 ring-slate-200',
  brand: 'bg-mesh-50 text-mesh-700 ring-mesh-200',
};

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  title?: string;
  className?: string;
}

export function Badge({ children, tone = 'muted', title, className = '' }: BadgeProps) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]} ${className}`.trim()}
    >
      {children}
    </span>
  );
}
