import type { ReactNode } from 'react';

import { Card } from './Card';

interface StatCardProps {
  label: string;
  value: string;
  hint?: ReactNode;
  tone?: 'default' | 'positive' | 'caution' | 'negative';
  icon?: ReactNode;
}

const VALUE_TONE: Record<NonNullable<StatCardProps['tone']>, string> = {
  default: 'text-ink',
  positive: 'text-positive-fg',
  caution: 'text-caution-fg',
  negative: 'text-negative-fg',
};

/**
 * One headline number. Used for the budget page's four top cards and the
 * dashboard's counts, so they share one set of proportions rather than two
 * that drift apart.
 */
export function StatCard({ label, value, hint, tone = 'default', icon }: StatCardProps) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-muted">{label}</p>
        {icon ? <span aria-hidden="true" className="text-lg leading-none">{icon}</span> : null}
      </div>
      <p className={`mt-2 text-2xl font-semibold tabular-nums ${VALUE_TONE[tone]}`}>
        {value}
      </p>
      {hint ? <div className="mt-1 text-xs text-muted">{hint}</div> : null}
    </Card>
  );
}
