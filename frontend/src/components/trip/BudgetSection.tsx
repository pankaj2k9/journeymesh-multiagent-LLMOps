import { useTranslation } from 'react-i18next';

import { useLanguage } from '../../hooks/useLanguage';
import type { BudgetAnalysis } from '../../types';
import { formatMoney } from '../../utils/format';
import { Badge } from '../common/Badge';
import type { BadgeTone } from '../common/Badge';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { SourceBadge } from '../common/SourceBadge';

const STATUS_TONES: Record<string, BadgeTone> = {
  within_budget: 'positive',
  near_limit: 'caution',
  over_budget: 'negative',
  insufficient_data: 'muted',
};

const LINES = ['flights', 'hotels', 'food', 'transport', 'activities', 'miscellaneous'] as const;

interface BudgetSectionProps {
  budget: BudgetAnalysis;
}

export function BudgetSection({ budget }: BudgetSectionProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const total = budget.breakdown?.total ?? budget.estimated_total;
  const hasData = total > 0;

  return (
    <Section
      id="budget"
      title={t('trip.budget')}
      actions={
        <Badge tone={STATUS_TONES[budget.budget_status] ?? 'muted'}>
          {t(`budgetPanel.status.${budget.budget_status}`)}
        </Badge>
      }
    >
      {!hasData ? (
        <EmptyState message={t('budgetPanel.empty')} />
      ) : (
        <div className="space-y-5">
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-muted">
                {t('budgetPanel.total')}
              </p>
              <p className="mt-0.5 text-lg font-semibold text-ink">
                {formatMoney(budget.estimated_total, budget.currency, language)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted">
                {t('budgetPanel.yourBudget')}
              </p>
              <p className="mt-0.5 text-lg font-semibold text-ink">
                {formatMoney(budget.total_budget, budget.currency, language)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted">
                {t('budgetPanel.remaining')}
              </p>
              <p
                className={`mt-0.5 text-lg font-semibold ${
                  (budget.remaining_budget ?? 0) < 0 ? 'text-negative-fg' : 'text-ink'
                }`}
              >
                {formatMoney(budget.remaining_budget, budget.currency, language)}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-muted">
                {t('budgetPanel.perTraveller')}
              </p>
              <p className="mt-0.5 text-lg font-semibold text-ink">
                {formatMoney(budget.per_traveler_total, budget.currency, language)}
              </p>
            </div>
          </div>

          <div>
            <h3 className="text-sm font-semibold text-ink">{t('budgetPanel.breakdown')}</h3>
            <ul className="mt-3 space-y-2">
              {LINES.map((line) => {
                const amount = budget.breakdown[line] ?? 0;
                const share = total > 0 ? Math.round((amount / total) * 100) : 0;
                const provenance = budget.line_provenance?.[line];
                return (
                  <li key={line}>
                    <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                      <span className="flex items-center gap-2 text-ink">
                        {t(`budgetPanel.lines.${line}`)}
                        {provenance ? <SourceBadge source={provenance.source} /> : null}
                      </span>
                      <span className="font-medium text-ink">
                        {formatMoney(amount, budget.currency, language)}
                      </span>
                    </div>
                    <div
                      className="mt-1 h-2 w-full overflow-hidden rounded-full bg-elevated"
                      role="presentation"
                    >
                      <div
                        className="h-full rounded-full bg-accent-soft0"
                        style={{ width: `${Math.min(share, 100)}%` }}
                      />
                    </div>
                    {provenance?.basis ? (
                      <p className="mt-1 text-xs text-muted">{provenance.basis}</p>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </div>

          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <p className="rounded-xl bg-elevated px-3 py-2 text-muted">
              {t('budgetPanel.confirmed')}:{' '}
              <span className="font-medium text-ink">
                {formatMoney(budget.confirmed_cost_total, budget.currency, language)}
              </span>
            </p>
            <p className="rounded-xl bg-elevated px-3 py-2 text-muted">
              {t('budgetPanel.estimated')}:{' '}
              <span className="font-medium text-ink">
                {formatMoney(budget.estimated_cost_total, budget.currency, language)}
              </span>
            </p>
          </div>

          {budget.recommendations.length ? (
            <div>
              <h3 className="text-sm font-semibold text-ink">
                {t('budgetPanel.recommendations')}
              </h3>
              <ul className="mt-2 space-y-1 text-sm text-muted">
                {budget.recommendations.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {budget.notes.length ? (
            <ul className="space-y-1 text-xs text-muted">
              {budget.notes.map((note) => (
                <li key={note}>• {note}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </Section>
  );
}
