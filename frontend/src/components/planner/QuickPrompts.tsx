import { useTranslation } from 'react-i18next';

import { QUICK_PROMPTS } from '../../utils/constants';

interface QuickPromptsProps {
  /** Fills the prompt box. Never submits - the traveller edits first. */
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}

/**
 * Example prompts under the main input.
 *
 * Driven entirely by QUICK_PROMPTS in utils/constants, so adding a destination
 * is a config entry rather than another block of JSX. Selecting one fills the
 * textarea and moves the caret there; it deliberately does not submit, because
 * the example is a starting point the traveller is expected to edit.
 */
export function QuickPrompts({ onSelect, disabled = false }: QuickPromptsProps) {
  const { t } = useTranslation();

  return (
    <div className="mt-3">
      <p className="text-xs text-muted" id="quick-prompts-label">
        {t('planner.quickPromptsLabel')}
      </p>
      <div
        className="mt-2 flex flex-wrap gap-2"
        role="group"
        aria-labelledby="quick-prompts-label"
      >
        {QUICK_PROMPTS.map((item) => (
          <button
            key={item.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(t(`planner.quickPrompts.${item.id}.prompt`))}
            className="inline-flex items-center gap-1.5 rounded-full border border-line-strong bg-elevated px-3 py-1.5 text-xs font-medium text-ink transition hover:border-accent hover:bg-accent-soft hover:text-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span aria-hidden="true">{item.flag}</span>
            {t(`planner.quickPrompts.${item.id}.label`)}
          </button>
        ))}
      </div>
    </div>
  );
}
