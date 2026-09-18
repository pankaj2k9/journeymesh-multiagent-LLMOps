import { useTranslation } from 'react-i18next';

import { StatCard } from '../common/StatCard';
import { useLanguage } from '../../hooks/useLanguage';
import type { TripBudget } from '../../types';
import { formatMoneyString, isNegative } from '../../utils/money';

/**
 * The four numbers at the top of the budget page.
 *
 * BOOKED and PLANNED are separate cards rather than one "spent" figure,
 * because the difference is the whole point: committed money is money the
 * traveller is on the hook for, planned money is a choice they can still
 * change. Collapsing them would make a fully refundable trip look identical to
 * a paid-for one.
 */
export function BudgetSummary({ budget }: { budget: TripBudget }) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const currency = budget.currency;

  const over = isNegative(budget.remaining_budget);

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label={t('budget.totalBudget')}
        value={
          budget.total_budget === null
            ? t('budget.notSet')
            : formatMoneyString(budget.total_budget, currency, language)
        }
        hint={
          budget.emergency_reserve && Number(budget.emergency_reserve) > 0
            ? t('budget.reserveHeld', {
                amount: formatMoneyString(budget.emergency_reserve, currency, language),
              })
            : undefined
        }
      />
      <StatCard
        label={t('budget.booked')}
        value={formatMoneyString(budget.committed_cost, currency, language)}
        hint={t('budget.bookedHint')}
      />
      <StatCard
        label={t('budget.planned')}
        value={formatMoneyString(budget.planned_cost, currency, language)}
        hint={t('budget.plannedHint')}
      />
      <StatCard
        label={t('budget.remaining')}
        value={
          budget.remaining_budget === null
            ? '—'
            : formatMoneyString(budget.remaining_budget, currency, language)
        }
        tone={over ? 'negative' : 'positive'}
        hint={over ? t('budget.overBudgetHint') : undefined}
      />
    </div>
  );
}
