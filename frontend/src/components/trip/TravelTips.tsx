import { useTranslation } from 'react-i18next';

import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';

interface TravelTipsProps {
  tips: string[];
  closingNote?: string | null;
}

export function TravelTips({ tips, closingNote }: TravelTipsProps) {
  const { t } = useTranslation();
  if (!tips.length && !closingNote) {
    return (
      <Section id="tips" title={t('trip.tips')}>
        <EmptyState message={t('trip.noData')} />
      </Section>
    );
  }

  return (
    <Section id="tips" title={t('trip.tips')}>
      <ul className="space-y-1.5 text-sm text-journey-slate">
        {tips.map((tip) => (
          <li key={tip}>• {tip}</li>
        ))}
      </ul>
      {closingNote ? (
        <p className="mt-3 rounded-xl bg-mesh-50 px-3 py-2 text-sm text-mesh-800">{closingNote}</p>
      ) : null}
    </Section>
  );
}
