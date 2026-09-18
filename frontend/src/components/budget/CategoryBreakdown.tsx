import { useTranslation } from 'react-i18next';

import { ProgressBar } from '../common/ProgressBar';
import { Section } from '../common/Card';
import { useLanguage } from '../../hooks/useLanguage';
import type { CategoryTotals, TripBudget } from '../../types';
import { formatMoneyString, parseMoney } from '../../utils/money';

const ROWS: { key: keyof CategoryTotals; labelKey: string; icon: string }[] = [
  { key: 'flight_cost', labelKey: 'budget.categories.flights', icon: '✈︎' },
  { key: 'accommodation_cost', labelKey: 'budget.categories.hotels', icon: '⌂' },
  { key: 'activity_cost', labelKey: 'budget.categories.activities', icon: '★' },
  { key: 'local_transport_cost', labelKey: 'budget.categories.transport', icon: '⇄' },
  { key: 'food_estimate', labelKey: 'budget.categories.food', icon: '◍' },
  { key: 'miscellaneous_estimate', labelKey: 'budget.categories.other', icon: '•' },
];

/**
 * Spend by category, each bar drawn as a share of the largest category rather
 * than of the budget. Against a budget, five small categories all render as
 * slivers and the breakdown stops being readable; against the largest line,
 * the shape of the spend is visible at a glance.
 */
export function CategoryBreakdown({ budget }: { budget: TripBudget }) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  const amounts = ROWS.map((row) => parseMoney(budget.categories[row.key]) ?? 0);
  const largest = Math.max(...amounts, 0);

  return (
    <Section title={t('budget.breakdownTitle')} description={t('budget.breakdownHint')}>
      <ul className="space-y-3">
        {ROWS.map((row, index) => {
          const amount = amounts[index];
          const share = largest > 0 ? (amount / largest) * 100 : 0;
          return (
            <li key={row.key}>
              <div className="flex items-baseline justify-between gap-3 text-sm">
                <span className="flex items-center gap-2 text-ink">
                  <span aria-hidden="true" className="text-muted">
                    {row.icon}
                  </span>
                  {t(row.labelKey)}
                </span>
                <span className="tabular-nums font-medium text-ink">
                  {formatMoneyString(budget.categories[row.key], budget.currency, language)}
                </span>
              </div>
              <ProgressBar
                className="mt-1.5"
                value={share}
                tone={amount > 0 ? 'brand' : 'muted'}
                label={t(row.labelKey)}
              />
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
