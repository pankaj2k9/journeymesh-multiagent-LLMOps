import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface CollapsibleProps {
  /** Rendered whether or not the section is open. Keep this to the summary. */
  summary?: ReactNode;
  /** Everything technical. Collapsed until the reader asks for it. */
  children: ReactNode;
  /** Open on first render. Defaults to false - details are never forced open. */
  defaultOpen?: boolean;
  /** Overrides the default "Show details" / "Hide details" wording. */
  showLabel?: string;
  hideLabel?: string;
  className?: string;
}

/**
 * The single Show details / Hide details disclosure used across the app.
 *
 * Agent execution notes, tool and provider information, evaluation dimensions
 * and every other technical panel goes through this component, so the
 * behaviour - collapsed by default, one button that swaps its own label - is
 * defined once rather than re-implemented per panel.
 *
 * The content is unmounted while collapsed rather than hidden with CSS, so a
 * screen reader and the keyboard tab order agree with what is on screen.
 */
export function Collapsible({
  summary,
  children,
  defaultOpen = false,
  showLabel,
  hideLabel,
  className = '',
}: CollapsibleProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(defaultOpen);
  const regionId = useId();

  return (
    <div className={className}>
      {summary ? <div>{summary}</div> : null}
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={regionId}
        className={`text-sm font-medium text-accent transition hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
          summary ? 'mt-3' : ''
        }`.trim()}
      >
        {open ? (hideLabel ?? t('common.hideDetails')) : (showLabel ?? t('common.showDetails'))}
      </button>
      {open ? (
        <div id={regionId} className="mt-3">
          {children}
        </div>
      ) : null}
    </div>
  );
}
