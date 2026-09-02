import { useTranslation } from 'react-i18next';

import type { Interest } from '../../types';
import { INTERESTS } from '../../utils/constants';

interface InterestPickerProps {
  value: Interest[];
  onChange: (next: Interest[]) => void;
}

export function InterestPicker({ value, onChange }: InterestPickerProps) {
  const { t } = useTranslation();

  const toggle = (interest: Interest) => {
    onChange(
      value.includes(interest)
        ? value.filter((item) => item !== interest)
        : [...value, interest],
    );
  };

  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t('planner.interests')}>
      {INTERESTS.map((interest) => {
        const selected = value.includes(interest);
        return (
          <button
            key={interest}
            type="button"
            aria-pressed={selected}
            onClick={() => toggle(interest)}
            className={`rounded-full px-3 py-1.5 text-sm transition ring-1 ring-inset ${
              selected
                ? 'bg-mesh-600 text-white ring-mesh-600'
                : 'bg-white text-journey-slate ring-slate-300 hover:ring-mesh-300'
            }`}
          >
            {t(`interests.${interest}`)}
          </button>
        );
      })}
    </div>
  );
}
