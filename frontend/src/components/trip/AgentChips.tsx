import { useTranslation } from 'react-i18next';

import { AGENT_DISPLAY, AGENT_LABELS } from '../../utils/constants';

interface AgentChipsProps {
  agents: string[];
  /** Marks agents that ran on the most recent pass. */
  highlighted?: string[];
  className?: string;
}

/**
 * The selected agents, rendered from AGENT_DISPLAY.
 *
 * Only the agents the supervisor actually chose appear here - a weather-only
 * question shows one chip, a full journey shows five - so the list is a
 * readable record of the routing decision rather than a fixed legend.
 */
export function AgentChips({ agents, highlighted, className = '' }: AgentChipsProps) {
  const { t } = useTranslation();
  if (!agents.length) return null;

  return (
    <ul className={`flex flex-wrap gap-2 ${className}`.trim()}>
      {agents.map((agent) => {
        const display = AGENT_DISPLAY[agent];
        const label = display
          ? t(display.labelKey, { defaultValue: AGENT_LABELS[agent] ?? agent })
          : (AGENT_LABELS[agent] ?? agent);
        const active = highlighted?.includes(agent);
        return (
          <li key={agent}>
            <span
              className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-medium ${
                active
                  ? 'border-accent bg-accent-soft text-accent'
                  : 'border-line-strong bg-elevated text-ink'
              }`}
            >
              <span aria-hidden="true">{display?.icon ?? '•'}</span>
              {label}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
