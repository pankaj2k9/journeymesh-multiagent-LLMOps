import { useTranslation } from 'react-i18next';

import type { TripDetailResponse } from '../../types';
import { contributingAgents } from '../../utils/agents';
import { AGENT_LABELS } from '../../utils/constants';
import { guardrailLabel, guardrailReason, summariseGuardrails } from '../../utils/guardrails';
import { Badge } from '../common/Badge';
import { Card } from '../common/Card';
import { Collapsible } from '../common/Collapsible';
import { AgentChips } from './AgentChips';

interface SupervisorPlanCardProps {
  trip: TripDetailResponse;
}

/**
 * The supervisor's execution plan.
 *
 * Summary first: whether the guardrails passed, why these agents were chosen,
 * and which ones they were. Everything technical - the per-check guardrail
 * trail, the change scope of a revision, the execution notes - stays behind
 * the Show details disclosure, because none of it is needed to read the plan.
 */
export function SupervisorPlanCard({ trip }: SupervisorPlanCardProps) {
  const { t } = useTranslation();
  const guardrails = summariseGuardrails(trip.guardrails);
  const agents = contributingAgents(trip);

  const lastChange = [...trip.reviews]
    .reverse()
    .find((review) => review.review_status === 'changes_requested');

  const hasDetails =
    guardrails.total > 0 || trip.messages.length > 0 || Boolean(lastChange?.change_scope.length);

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-accent">
            {t('supervisor.eyebrow')}
          </p>
          <h2 className="mt-1 text-lg font-semibold text-ink">{t('supervisor.title')}</h2>
        </div>
        <Badge tone={guardrails.passed ? 'positive' : 'negative'}>
          {guardrails.passed ? t('supervisor.guardrailPassed') : t('supervisor.guardrailBlocked')}
        </Badge>
      </div>

      {trip.execution_reason ? (
        <p className="mt-4 text-sm leading-relaxed text-ink">{trip.execution_reason}</p>
      ) : null}

      {agents.length ? (
        <>
          <p className="mt-4 text-xs uppercase tracking-wide text-muted">
            {t('supervisor.selectedAgents')}
          </p>
          <AgentChips
            agents={agents}
            highlighted={trip.revision > 1 ? trip.selected_agents : undefined}
            className="mt-2"
          />
          {trip.revision > 1 && trip.selected_agents.length ? (
            <p className="mt-2 text-xs text-muted">
              {t('supervisor.rerunNote', {
                agents: trip.selected_agents
                  .map((agent) => AGENT_LABELS[agent] ?? agent)
                  .join(', '),
              })}
            </p>
          ) : null}
        </>
      ) : null}

      {hasDetails ? (
        <Collapsible className="mt-4 border-t border-line pt-4">
          {guardrails.total ? (
            <div>
              <h3 className="text-xs uppercase tracking-wide text-muted">
                {t('supervisor.guardrailChecks', { count: guardrails.total })}
              </h3>
              <ul className="mt-2 space-y-1.5 text-sm">
                {guardrails.records.map((record, index) => {
                  const reason = guardrailReason(record);
                  return (
                    <li
                      key={`${record.stage ?? 'stage'}-${index}`}
                      className="flex flex-wrap items-center gap-2"
                    >
                      <Badge tone={record.allowed === false ? 'negative' : 'positive'}>
                        {record.allowed === false
                          ? t('supervisor.blocked')
                          : t('supervisor.passed')}
                      </Badge>
                      <span className="text-ink">{guardrailLabel(record)}</span>
                      {reason ? <span className="text-muted">— {reason}</span> : null}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          {lastChange?.change_scope.length ? (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-muted">
                {t('supervisor.changeScope')}
              </h3>
              <p className="mt-1 text-sm text-muted">
                {lastChange.change_scope
                  .map((agent) => AGENT_LABELS[agent] ?? agent)
                  .join(', ')}
              </p>
            </div>
          ) : null}

          {trip.messages.length ? (
            <div className="mt-4">
              <h3 className="text-xs uppercase tracking-wide text-muted">
                {t('supervisor.executionLog')}
              </h3>
              <ul className="mt-1 space-y-1 text-sm text-muted">
                {trip.messages.map((message, index) => (
                  <li key={`${index}-${message.slice(0, 24)}`}>• {message}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </Collapsible>
      ) : null}
    </Card>
  );
}
