import { useTranslation } from 'react-i18next';

import type { EvaluationResult } from '../../types';
import { scoreTone } from '../../utils/format';
import { Badge } from '../common/Badge';
import { Section } from '../common/Card';

interface EvaluationPanelProps {
  evaluation: EvaluationResult;
}

export function EvaluationPanel({ evaluation }: EvaluationPanelProps) {
  const { t } = useTranslation();
  const tone = scoreTone(evaluation.overall_score);
  const percent = Math.round(evaluation.overall_score * 100);

  return (
    <Section
      id="quality"
      title={t('trip.quality')}
      description={t('evaluation.mode', { value: evaluation.mode })}
      actions={
        <Badge tone={tone}>
          {t('evaluation.score')}: {percent}%
        </Badge>
      }
    >
      <p className="text-sm text-journey-slate">
        {evaluation.passed ? t('evaluation.passed') : t('evaluation.attention')}
      </p>

      {Object.keys(evaluation.dimension_scores).length ? (
        <div className="mt-3">
          <h3 className="text-xs uppercase tracking-wide text-journey-slate">
            {t('evaluation.dimensions')}
          </h3>
          <ul className="mt-2 grid gap-2 sm:grid-cols-2">
            {Object.entries(evaluation.dimension_scores).map(([dimension, score]) => {
              const label = t(`evaluation.names.${dimension}`);
              return (
                <li key={dimension} className="flex items-center gap-3">
                  <span className="w-40 shrink-0 text-xs text-journey-slate">
                    {label.startsWith('evaluation.') ? dimension : label}
                  </span>
                  <span className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
                    <span
                      className={`block h-full rounded-full ${
                        score >= 0.8
                          ? 'bg-emerald-500'
                          : score >= 0.6
                            ? 'bg-amber-500'
                            : 'bg-rose-500'
                      }`}
                      style={{ width: `${Math.round(score * 100)}%` }}
                    />
                  </span>
                  <span className="w-10 text-right text-xs text-journey-slate">
                    {Math.round(score * 100)}%
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      ) : null}

      {evaluation.failures.length ? (
        <div className="mt-4">
          <h3 className="text-xs uppercase tracking-wide text-rose-700">
            {t('evaluation.failures')}
          </h3>
          <ul className="mt-1 space-y-1 text-sm text-rose-700">
            {evaluation.failures.map((failure) => (
              <li key={failure}>• {failure}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {evaluation.warnings.length ? (
        <div className="mt-4">
          <h3 className="text-xs uppercase tracking-wide text-amber-700">
            {t('evaluation.warnings')}
          </h3>
          <ul className="mt-1 space-y-1 text-sm text-amber-800">
            {evaluation.warnings.map((warning) => (
              <li key={warning}>• {warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </Section>
  );
}
