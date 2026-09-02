import { useTranslation } from 'react-i18next';

import type { TravelStyle } from '../../types';
import { TRAVEL_STYLES } from '../../utils/constants';

interface TravelStylePickerProps {
  value: TravelStyle | '';
  onChange: (next: TravelStyle | '') => void;
}

export function TravelStylePicker({ value, onChange }: TravelStylePickerProps) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={t('planner.travelStyle')}>
      {TRAVEL_STYLES.map((style) => {
        const selected = value === style;
        return (
          <button
            key={style}
            type="button"
            aria-pressed={selected}
            onClick={() => onChange(selected ? '' : style)}
            className={`rounded-xl px-3 py-1.5 text-sm transition ring-1 ring-inset ${
              selected
                ? 'bg-journey-ink text-white ring-journey-ink'
                : 'bg-white text-journey-slate ring-slate-300 hover:ring-journey-ink/40'
            }`}
          >
            {t(`styles.${style}`)}
          </button>
        );
      })}
    </div>
  );
}
