import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../common/Button';
import { Field, inputClass } from '../planner/Field';

interface RequestChangesFormProps {
  onSubmit: (changes: string) => void;
  onApprove: () => void;
  approving?: boolean;
  submitting?: boolean;
  disabled?: boolean;
}

/**
 * The human-in-the-loop decision.
 *
 * The feedback box is always visible rather than hidden behind a toggle, so
 * both decisions - approve as it stands, or revise with a note - are one click
 * away from reading the draft. Approving does not require the box to be
 * filled; revising validates it first, because an empty change request would
 * spend a revision from a bounded budget for nothing.
 *
 * Each button carries its own spinner and disables the other while it runs, so
 * a slow revision cannot be approved out from under itself.
 */
export function RequestChangesForm({
  onSubmit,
  onApprove,
  approving = false,
  submitting = false,
  disabled = false,
}: RequestChangesFormProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | undefined>();

  const busy = approving || submitting || disabled;

  const handleSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = value.trim();
    if (trimmed.length < 5) {
      setError(t('review.changesTooShort'));
      return;
    }
    setError(undefined);
    onSubmit(trimmed);
  };

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-3" noValidate>
      <Field
        label={t('review.changesLabel')}
        htmlFor="requestedChanges"
        hint={t('review.changesHelp')}
        error={error}
      >
        <textarea
          id="requestedChanges"
          rows={3}
          className={`${inputClass} resize-y`}
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={t('review.changesPlaceholder')}
          maxLength={2000}
          aria-invalid={Boolean(error)}
          disabled={busy}
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          onClick={onApprove}
          loading={approving}
          disabled={submitting || disabled}
        >
          {approving ? t('review.approving') : t('review.approve')}
        </Button>
        <Button
          type="submit"
          variant="secondary"
          loading={submitting}
          disabled={approving || disabled}
        >
          {submitting ? t('review.submittingChanges') : t('review.submitChanges')}
        </Button>
      </div>
    </form>
  );
}
