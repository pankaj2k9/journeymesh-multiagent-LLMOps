import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../common/Button';
import { Callout } from '../common/Callout';
import { Section } from '../common/Card';
import type { BudgetCategory, ExpenseBody } from '../../types';

const CATEGORIES: BudgetCategory[] = [
  'FLIGHT',
  'ACCOMMODATION',
  'ACTIVITY',
  'LOCAL_TRANSPORT',
  'FOOD',
  'MISCELLANEOUS',
];

interface AddExpenseFormProps {
  currency: string;
  onSubmit: (body: ExpenseBody) => void;
  submitting: boolean;
  errorMessage?: string | null;
}

/**
 * Manual expense entry.
 *
 * Only ESTIMATED and PAID are offered, and that is a rule the server enforces
 * too: SELECTED and BOOKED belong to the selection and booking flows, so a
 * form must never be able to claim that something was booked.
 *
 * The amount is kept as text all the way to the API. Parsing it into a float
 * here would reintroduce exactly the drift the string wire format exists to
 * prevent.
 */
export function AddExpenseForm({
  currency,
  onSubmit,
  submitting,
  errorMessage,
}: AddExpenseFormProps) {
  const { t } = useTranslation();
  const [category, setCategory] = useState<BudgetCategory>('MISCELLANEOUS');
  const [label, setLabel] = useState('');
  const [amount, setAmount] = useState('');
  const [state, setState] = useState<'ESTIMATED' | 'PAID'>('ESTIMATED');
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    setLocalError(null);

    const trimmed = amount.trim();
    if (!label.trim()) {
      setLocalError(t('budget.errors.labelRequired'));
      return;
    }
    // A shape check only. The server validates the amount properly; this is
    // here so a typo is caught before a round trip, not so the client decides.
    if (!/^\d+(\.\d{1,4})?$/.test(trimmed)) {
      setLocalError(t('budget.errors.amountInvalid'));
      return;
    }

    onSubmit({
      category,
      label: label.trim(),
      amount: trimmed,
      state,
      currency,
    });
    setLabel('');
    setAmount('');
  };

  const fieldClass =
    'w-full rounded-xl border border-line bg-surface px-3 py-2 text-sm text-ink ' +
    'focus:border-accent focus:outline-none focus:ring-2 focus:ring-accent/30';

  return (
    <Section title={t('budget.addTitle')} description={t('budget.addHint')}>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              {t('budget.fieldLabel')}
            </span>
            <input
              className={fieldClass}
              value={label}
              maxLength={200}
              onChange={(event) => setLabel(event.target.value)}
              placeholder={t('budget.labelPlaceholder')}
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              {t('budget.fieldAmount', { currency })}
            </span>
            <input
              className={`${fieldClass} tabular-nums`}
              value={amount}
              inputMode="decimal"
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0.00"
            />
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              {t('budget.fieldCategory')}
            </span>
            <select
              className={fieldClass}
              value={category}
              onChange={(event) => setCategory(event.target.value as BudgetCategory)}
            >
              {CATEGORIES.map((value) => (
                <option key={value} value={value}>
                  {t(`budget.categories.short.${value}`)}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="mb-1 block text-xs font-medium text-muted">
              {t('budget.fieldState')}
            </span>
            <select
              className={fieldClass}
              value={state}
              onChange={(event) => setState(event.target.value as 'ESTIMATED' | 'PAID')}
            >
              <option value="ESTIMATED">{t('budget.states.ESTIMATED')}</option>
              <option value="PAID">{t('budget.states.PAID')}</option>
            </select>
          </label>
        </div>

        {localError || errorMessage ? (
          <Callout tone="danger" title={t('errors.title')}>
            {localError ?? errorMessage}
          </Callout>
        ) : null}

        <Button type="submit" loading={submitting}>
          {t('budget.addAction')}
        </Button>
      </form>
    </Section>
  );
}
