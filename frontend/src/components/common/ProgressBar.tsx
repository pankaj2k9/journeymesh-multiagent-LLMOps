import type { BadgeTone } from './Badge';

const TRACK = 'h-2 w-full overflow-hidden rounded-full bg-neutral-bg';

const FILL: Record<BadgeTone, string> = {
  positive: 'bg-positive-fg',
  neutral: 'bg-info-fg',
  caution: 'bg-caution-fg',
  negative: 'bg-negative-fg',
  muted: 'bg-neutral-fg',
  brand: 'bg-accent',
};

interface ProgressBarProps {
  /** 0-100. Values outside the range are clamped by the caller. */
  value: number;
  tone?: BadgeTone;
  label: string;
  /** The value announced to a screen reader, when it differs from `value`. */
  valueText?: string;
  className?: string;
}

/**
 * A meter, not a decoration: it carries `role="progressbar"` with its bounds,
 * so a budget that is 96% spent is as legible to a screen reader as it is to
 * an eye. The visible number always lives next to it in the calling component,
 * because a bar alone cannot say "$700 remaining".
 */
export function ProgressBar({
  value,
  tone = 'brand',
  label,
  valueText,
  className = '',
}: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(value) ? value : 0));
  return (
    <div
      role="progressbar"
      aria-valuenow={Math.round(clamped)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuetext={valueText}
      aria-label={label}
      className={`${TRACK} ${className}`.trim()}
    >
      <div
        className={`h-full rounded-full transition-all duration-500 ${FILL[tone]}`}
        style={{ width: `${clamped}%` }}
      />
    </div>
  );
}
