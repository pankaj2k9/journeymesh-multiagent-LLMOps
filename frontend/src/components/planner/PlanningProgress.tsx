import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Card } from '../common/Card';

/**
 * What JourneyMesh is doing while a journey is being planned.
 *
 * The backend answers in one call, so this is an honest paraphrase of the
 * pipeline rather than live progress - it advances on a timer and stops at the
 * last step until the response arrives. Each step is announced politely, and
 * the current step is marked by an icon and text, not by colour alone.
 */
const STEPS = [
  'planner.progress.guardrails',
  'planner.progress.supervisor',
  'planner.progress.specialists',
  'planner.progress.evaluation',
  'planner.progress.review',
] as const;

const STEP_MS = 2200;

export function PlanningProgress() {
  const { t } = useTranslation();
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setActive((current) => Math.min(current + 1, STEPS.length - 1));
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <Card className="p-5">
      <p className="text-sm font-semibold text-ink">{t('planner.progress.title')}</p>
      <ol className="mt-3 space-y-2" aria-live="polite">
        {STEPS.map((step, index) => {
          const done = index < active;
          const current = index === active;
          return (
            <li key={step} className="flex items-center gap-3 text-sm">
              <span
                aria-hidden="true"
                className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold ${
                  done
                    ? 'border-positive-line bg-positive-bg text-positive-fg'
                    : current
                      ? 'border-accent bg-accent-soft text-accent'
                      : 'border-line bg-elevated text-faint'
                }`}
              >
                {done ? '\u2713' : index + 1}
              </span>
              <span className={current || done ? 'text-ink' : 'text-muted'}>
                {t(step)}
                {current ? (
                  <span className="ml-2 text-xs text-muted">{t('common.loading')}</span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
