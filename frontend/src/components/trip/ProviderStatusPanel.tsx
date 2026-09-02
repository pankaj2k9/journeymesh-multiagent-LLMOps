import { useTranslation } from 'react-i18next';

import type { ProviderStatus } from '../../types';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';
import { Badge } from '../common/Badge';

interface ProviderStatusPanelProps {
  statuses: ProviderStatus[];
}

export function ProviderStatusPanel({ statuses }: ProviderStatusPanelProps) {
  const { t } = useTranslation();

  // Collapse repeated calls to the same provider into one row.
  const grouped = statuses.reduce<Record<string, { ok: number; total: number; item: ProviderStatus }>>(
    (accumulator, status) => {
      const key = `${status.provider}:${status.kind}`;
      const entry = accumulator[key] ?? { ok: 0, total: 0, item: status };
      entry.total += 1;
      if (status.ok) entry.ok += 1;
      entry.item = status.ok ? status : entry.item;
      accumulator[key] = entry;
      return accumulator;
    },
    {},
  );

  const rows = Object.entries(grouped);

  return (
    <Section id="providers" title={t('trip.providers')}>
      {rows.length === 0 ? (
        <EmptyState message={t('trip.noData')} />
      ) : (
        <ul className="divide-y divide-slate-100 text-sm">
          {rows.map(([key, entry]) => (
            <li key={key} className="flex flex-wrap items-center justify-between gap-2 py-2">
              <span className="font-medium text-journey-ink">{entry.item.provider}</span>
              <span className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-journey-slate">
                  {entry.ok}/{entry.total}
                </span>
                {entry.item.latency_ms !== null && entry.item.latency_ms !== undefined ? (
                  <span className="text-xs text-journey-slate">{entry.item.latency_ms} ms</span>
                ) : null}
                <SourceBadge source={entry.item.source} />
                <Badge tone={entry.ok === entry.total ? 'positive' : 'caution'}>
                  {entry.ok === entry.total ? 'ok' : 'partial'}
                </Badge>
              </span>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}
