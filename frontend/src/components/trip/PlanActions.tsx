import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { TripDetailResponse } from '../../types';
import { buildPlanMarkdown, planFileName } from '../../utils/planText';
import { Button } from '../common/Button';

interface PlanActionsProps {
  trip: TripDetailResponse;
}

type Feedback = 'copied' | 'copyFailed' | null;

/**
 * The header of the plan: what it is, which thread produced it, and the three
 * things a traveller wants to do with it.
 *
 * Copy and Download share one renderer (utils/planText), so the clipboard and
 * the file can never disagree. "Save as PDF" opens the browser's own print
 * dialogue against the print stylesheet rather than pulling in a PDF library -
 * the output is a real PDF and the bundle gains no dependency.
 */
export function PlanActions({ trip }: PlanActionsProps) {
  const { t } = useTranslation();
  const [feedback, setFeedback] = useState<Feedback>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const announce = (value: Feedback) => {
    setFeedback(value);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setFeedback(null), 2500);
  };

  const handleCopy = async () => {
    const text = buildPlanMarkdown(trip, t);
    try {
      await navigator.clipboard.writeText(text);
      announce('copied');
    } catch {
      announce('copyFailed');
    }
  };

  const handleDownload = () => {
    const text = buildPlanMarkdown(trip, t);
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = planFileName(trip);
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  };

  const approved = trip.review_status === 'approved';

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 print:block">
      <div>
        <h2 className="text-lg font-semibold text-ink">
          {approved ? t('trip.finalTitle') : t('trip.draftTitle')}
        </h2>
        <p className="mt-1 font-mono text-xs text-muted">
          {t('trip.threadId')}: {trip.trip_id}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2 print:hidden">
        <Button variant="secondary" size="sm" onClick={() => void handleCopy()}>
          {t('trip.copy')}
        </Button>
        <Button variant="secondary" size="sm" onClick={handleDownload}>
          {t('trip.download')}
        </Button>
        <Button variant="secondary" size="sm" onClick={() => window.print()}>
          {t('trip.savePdf')}
        </Button>
      </div>
      <p className="sr-only" role="status" aria-live="polite">
        {feedback ? t(`trip.${feedback}`) : ''}
      </p>
      {feedback ? (
        <p
          className={`w-full text-xs ${
            feedback === 'copied' ? 'text-positive-fg' : 'text-negative-fg'
          } print:hidden`}
        >
          {t(`trip.${feedback}`)}
        </p>
      ) : null}
    </div>
  );
}
