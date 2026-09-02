import type { ReactNode } from 'react';

export type BadgeTone = 'positive' | 'neutral' | 'caution' | 'negative' | 'muted' | 'brand';

// Each tone resolves through the theme tokens, so a badge is legible on both
// the light sand ground and the dark slate one without a second class list.
const TONES: Record<BadgeTone, string> = {
  positive: 'bg-positive-bg text-positive-fg ring-positive-line',
  neutral: 'bg-info-bg text-info-fg ring-info-line',
  caution: 'bg-caution-bg text-caution-fg ring-caution-line',
  negative: 'bg-negative-bg text-negative-fg ring-negative-line',
  muted: 'bg-neutral-bg text-neutral-fg ring-neutral-line',
  brand: 'bg-brand-bg text-brand-fg ring-brand-line',
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
