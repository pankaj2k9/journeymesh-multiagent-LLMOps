import type { City } from '../../utils/cities';
import { inputClass } from './Field';

interface CityPickerProps {
  id: string;
  value: string;
  onChange: (next: string) => void;
  cities: City[];
  placeholder: string;
  /** A city that cannot be picked here, e.g. the origin when choosing a destination. */
  exclude?: string;
  invalid?: boolean;
}

/**
 * A free-text city field with one-tap suggestions underneath. The chips are a
 * shortcut; typing any other city still works.
 */
export function CityPicker({
  id,
  value,
  onChange,
  cities,
  placeholder,
  exclude = '',
  invalid = false,
}: CityPickerProps) {
  const excluded = exclude.trim().toLowerCase();
  const current = value.trim().toLowerCase();
  const shown = cities.filter((city) => city.name.toLowerCase() !== excluded);

  return (
    <div className="space-y-2">
      <input
        id={id}
        className={inputClass}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        maxLength={120}
        aria-invalid={invalid}
        autoComplete="off"
      />
      <div
        className="flex max-h-24 flex-wrap gap-1.5 overflow-y-auto"
        role="group"
        aria-label={placeholder}
      >
        {shown.map((city) => {
          const selected = current === city.name.toLowerCase();
          return (
            <button
              key={city.code}
              type="button"
              aria-pressed={selected}
              onClick={() => onChange(selected ? '' : city.name)}
              className="jm-chip px-2.5 py-1 text-xs"
            >
              <span className="font-semibold">{city.code}</span>
              <span>{city.name}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
