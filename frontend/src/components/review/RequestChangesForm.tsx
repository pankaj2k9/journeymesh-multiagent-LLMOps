import { useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '../common/Button';
import { Field, inputClass } from '../planner/Field';

interface RequestChangesFormProps {
  onSubmit: (changes: string) => void;
  onCancel: () => void;
  submitting?: boolean;
}

export function RequestChangesForm({
  onSubmit,
  onCancel,
  submitting = false,
}: RequestChangesFormProps) {
  const { t } = useTranslation();
  const [value, setValue] = useState('');
  const [error, setError] = useState<string | undefined>();

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
        />
      </Field>
      <div className="flex flex-wrap gap-2">
        <Button type="submit" loading={submitting}>
          {submitting ? t('review.submittingChanges') : t('review.submitChanges')}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel} disabled={submitting}>
          {t('review.cancel')}
        </Button>
      </div>
    </form>
  );
}
