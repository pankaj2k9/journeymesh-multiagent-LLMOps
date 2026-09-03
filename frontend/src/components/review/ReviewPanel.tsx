import { useTranslation } from 'react-i18next';

import { AGENT_LABELS } from '../../utils/constants';
import type { ReviewRecord, ReviewStatus } from '../../types';
import { Button } from '../common/Button';
import { Callout } from '../common/Callout';
import { Card } from '../common/Card';
import { RequestChangesForm } from './RequestChangesForm';

interface ReviewPanelProps {
  status: ReviewStatus;
  revision: number;
  maxRevisions: number;
  reviews: ReviewRecord[];
  approving: boolean;
  requesting: boolean;
  errorMessage?: string | null;
  onApprove: () => void;
  onRequestChanges: (changes: string) => void;
  onRetry?: () => void;
}

function agentNames(agents: string[]): string {
  return agents.map((agent) => AGENT_LABELS[agent] ?? agent).join(', ');
}

export function ReviewPanel({
  status,
  revision,
  maxRevisions,
  reviews,
  approving,
  requesting,
  errorMessage,
  onApprove,
  onRequestChanges,
  onRetry,
}: ReviewPanelProps) {
  const { t } = useTranslation();

  const approved = status === 'approved';
  const limitReached = status === 'revision_limit_reached';
  const lastChange = [...reviews]
    .reverse()
    .find((review) => review.review_status === 'changes_requested');

  return (
    <Card className="border-accent/35 bg-surface p-5 sm:p-6 print:hidden">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            {t('review.eyebrow')}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-ink">{t('review.title')}</h2>
          <p className="mt-1 text-sm text-muted">{t('review.subtitle')}</p>
        </div>
        <p className="text-xs text-muted">
          {t('review.revisionsUsed', { used: revision, max: maxRevisions })}
        </p>
      </div>

      {revision > 1 && !approved ? (
        <p className="mt-3 text-sm font-medium text-accent">
          {t('review.revisionReady', { count: revision })}
        </p>
      ) : null}

      {lastChange && lastChange.selected_agents.length ? (
        <div className="mt-3 space-y-1 text-xs text-muted">
          <p>{t('review.rerunAgents', { agents: agentNames(lastChange.selected_agents) })}</p>
        </div>
      ) : null}

      {errorMessage ? (
        <div className="mt-4">
          <Callout
            tone="danger"
            title={t('errors.title')}
            actions={
              onRetry ? (
                <Button variant="secondary" size="sm" onClick={onRetry}>
                  {t('errors.retry')}
                </Button>
              ) : undefined
            }
          >
            {errorMessage}
          </Callout>
        </div>
      ) : null}

      {approved ? (
        <div className="mt-4">
          <Callout tone="success">{t('review.approved')}</Callout>
        </div>
      ) : limitReached ? (
        <div className="mt-4 space-y-3">
          <Callout tone="warning">{t('review.limitReached')}</Callout>
          <Button onClick={onApprove} loading={approving}>
            {approving ? t('review.approving') : t('review.approve')}
          </Button>
        </div>
      ) : (
        <RequestChangesForm
          approving={approving}
          submitting={requesting}
          onApprove={onApprove}
          onSubmit={onRequestChanges}
        />
      )}
    </Card>
  );
}
