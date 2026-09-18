import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { AddExpenseForm } from './AddExpenseForm';
import { BudgetSummary } from './BudgetSummary';
import { CategoryBreakdown } from './CategoryBreakdown';
import { ExpenseLedger } from './ExpenseLedger';
import { ApiError } from '../../api/client';
import { Callout } from '../common/Callout';
import { ProgressBar } from '../common/ProgressBar';
import { Card } from '../common/Card';
import { SkeletonCard } from '../common/Skeleton';
import { Button } from '../common/Button';
import { useAddExpense, useBudget, useLedger, useReverseExpense } from '../../hooks/useBudget';
import { useLanguage } from '../../hooks/useLanguage';
import type { ExpenseBody } from '../../types';
import { barPercent, formatMoneyString } from '../../utils/money';

/**
 * The budget page for one journey.
 *
 * Every figure comes from the budget endpoint. Nothing here adds two amounts
 * together: the backend owns the arithmetic, and an interface that recomputed
 * a total would eventually disagree with the number the traveller is charged.
 */
export function BudgetTab({ tripId }: { tripId: string }) {
  const { t } = useTranslation();
  const { language } = useLanguage();
  const budget = useBudget(tripId);
  const ledger = useLedger(tripId);
  const addExpense = useAddExpense(tripId);
  const reverseExpense = useReverseExpense(tripId);
  const [formError, setFormError] = useState<string | null>(null);

  if (budget.isLoading) {
    return (
      <div className="space-y-3" role="status" aria-label={t('common.loading')}>
        <SkeletonCard />
        <SkeletonCard />
      </div>
    );
  }

  if (budget.isError || !budget.data) {
    return (
      <div className="space-y-3">
        <Callout tone="danger" title={t('errors.title')}>
          {t('errors.network')}
        </Callout>
        <Button variant="secondary" onClick={() => void budget.refetch()}>
          {t('errors.retry')}
        </Button>
      </div>
    );
  }

  const data = budget.data;
  const used = data.percentage_used;

  const submit = (body: ExpenseBody) => {
    setFormError(null);
    addExpense.mutate(body, {
      onError: (error: unknown) => {
        setFormError(error instanceof ApiError ? error.message : t('errors.title'));
      },
    });
  };

  return (
    <div className="space-y-5">
      <BudgetSummary budget={data} />

      {data.total_budget !== null ? (
        <Card className="p-4 sm:p-5">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-sm font-semibold text-ink">{t('budget.allocatedTitle')}</h2>
            <p className="text-sm tabular-nums text-muted">
              {t('dashboard.remainingOf', {
                remaining: formatMoneyString(data.allocated_cost, data.currency, language),
                total: formatMoneyString(data.total_budget, data.currency, language),
              })}
              {used !== null ? ` · ${Math.round(used)}%` : ''}
            </p>
          </div>
          <ProgressBar
            className="mt-2"
            value={barPercent(used)}
            tone={
              data.verdict === 'over_budget'
                ? 'negative'
                : data.verdict === 'near_limit'
                  ? 'caution'
                  : 'positive'
            }
            label={t('dashboard.budgetUsedLabel')}
            valueText={
              used !== null ? t('dashboard.percentUsed', { percent: Math.round(used) }) : undefined
            }
          />
          {data.verdict === 'over_budget' ? (
            <Callout tone="danger" title={t('budget.overBudgetTitle')}>
              {t('budget.overBudgetBody')}
            </Callout>
          ) : null}
        </Card>
      ) : (
        <Callout tone="info" title={t('budget.noBudgetTitle')}>
          {t('budget.noBudgetBody')}
        </Callout>
      )}

      <CategoryBreakdown budget={data} />

      <AddExpenseForm
        currency={data.currency}
        onSubmit={submit}
        submitting={addExpense.isPending}
        errorMessage={formError}
      />

      {ledger.isLoading ? (
        <SkeletonCard />
      ) : (
        <ExpenseLedger
          items={ledger.data?.items ?? []}
          currency={data.currency}
          onRemove={(itemId) => reverseExpense.mutate(itemId)}
          removingId={
            reverseExpense.isPending ? (reverseExpense.variables as string) : null
          }
        />
      )}
    </div>
  );
}
