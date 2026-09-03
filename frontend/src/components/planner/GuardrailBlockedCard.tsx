import { useTranslation } from 'react-i18next';

import type { GuardrailBlockedResponse } from '../../types';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { Collapsible } from '../common/Collapsible';

interface GuardrailBlockedCardProps {
  blocked: GuardrailBlockedResponse;
}

/**
 * What a refused request looks like.
 *
 * The supervisor never ran, no agent was selected, no tool was called and no
 * provider was contacted - the input guardrail refused before the graph
 * started. The card says so plainly, in the same place the execution plan
 * would otherwise appear, so the absence of agents reads as a decision rather
 * than a failure.
 */
export function GuardrailBlockedCard({ blocked }: GuardrailBlockedCardProps) {
  const { t } = useTranslation();

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            {t('supervisor.eyebrow')}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-ink">{t('supervisor.title')}</h2>
        </div>
        <Badge tone="negative">{t('supervisor.guardrailBlocked')}</Badge>
      </div>

      <p className="mt-4 text-sm leading-relaxed text-ink">{blocked.message}</p>
      {blocked.guidance ? (
        <p className="mt-2 text-sm text-muted">{blocked.guidance}</p>
      ) : null}

      <Collapsible className="mt-4 border-t border-line pt-4">
        <dl className="space-y-2 text-sm">
          <div className="flex flex-wrap gap-2">
            <dt className="text-muted">{t('supervisor.reasonCode')}</dt>
            <dd className="font-mono text-ink">{blocked.reason_code}</dd>
          </div>
          <div className="flex flex-wrap gap-2">
            <dt className="text-muted">{t('supervisor.agentsRun')}</dt>
            <dd className="text-ink">{t('supervisor.noAgentsRun')}</dd>
          </div>
        </dl>
      </Collapsible>
    </Card>
  );
}
