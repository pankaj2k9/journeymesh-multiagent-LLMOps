import { useTranslation } from 'react-i18next';

import { Badge } from '../common/Badge';
import { Button } from '../common/Button';
import { EmptyState } from '../common/EmptyState';
import { Section } from '../common/Card';
import { useLanguage } from '../../hooks/useLanguage';
import type { BudgetItem, BudgetItemState } from '../../types';
import { formatDateTime } from '../../utils/format';
import { formatMoneyExact, parseMoney } from '../../utils/money';

const STATE_TONE: Record<BudgetItemState, 'positive' | 'neutral' | 'caution' | 'muted'> = {
  PAID: 'positive',
  BOOKED: 'positive',
  SELECTED: 'neutral',
  ESTIMATED: 'caution',
};

interface ExpenseLedgerProps {
  items: BudgetItem[];
  currency: string;
  onRemove: (itemId: string) => void;
  removingId?: string | null;
}

/**
 * The transaction history behind the budget.
 *
 * Reversals are shown, not filtered out, and a reversed line keeps its place:
 * "Museum removed −$80" is the audit trail the budget engine deliberately
 * writes, and hiding it would leave a total that moved for no visible reason.
 */
export function ExpenseLedger({
  items,
  currency,
  onRemove,
  removingId,
}: ExpenseLedgerProps) {
  const { t } = useTranslation();
  const { language } = useLanguage();

  if (items.length === 0) {
    return (
      <Section title={t('budget.historyTitle')} description={t('budget.historyHint')}>
        <EmptyState message={t('budget.historyEmpty')} />
      </Section>
    );
  }

  const reversedIds = new Set(
    items.map((item) => item.reverses_id).filter((value): value is string => Boolean(value)),
  );

  return (
    <Section title={t('budget.historyTitle')} description={t('budget.historyHint')}>
      <ul className="divide-y divide-line">
        {items.map((item) => {
          const amount = parseMoney(item.amount) ?? 0;
          const isReversal = item.reverses_id !== null;
          const alreadyReversed = reversedIds.has(item.id);
          return (
            <li key={item.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p
                  className={`truncate text-sm ${
                    isReversal || alreadyReversed
                      ? 'text-muted line-through'
                      : 'font-medium text-ink'
                  }`}
                >
                  {item.label || t('budget.untitledLine')}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  <Badge tone={STATE_TONE[item.state]}>{t(`budget.states.${item.state}`)}</Badge>
                  <span>{t(`budget.categories.short.${item.category}`)}</span>
                  <span aria-hidden="true">·</span>
                  <span>{formatDateTime(item.created_at, language)}</span>
                </p>
              </div>

              <span
                className={`tabular-nums text-sm font-semibold ${
                  amount < 0 ? 'text-positive-fg' : 'text-ink'
                }`}
              >
                {amount >= 0 ? '+' : ''}
                {formatMoneyExact(item.amount, item.currency || currency, language)}
              </span>

              {!isReversal && !alreadyReversed ? (
                <Button
                  size="sm"
                  variant="ghost"
                  loading={removingId === item.id}
                  onClick={() => onRemove(item.id)}
                  aria-label={t('budget.removeLine', { label: item.label })}
                >
                  {t('budget.remove')}
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}
