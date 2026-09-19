interface Choice<T extends string> {
  value: T;
  label: string;
  hint?: string;
  icon?: string;
}

interface ChoiceChipsProps<T extends string> {
  label: string;
  choices: Choice<T>[];
  value: T | '';
  onChange: (next: T | '') => void;
  /** When false, pressing the selected chip again keeps it selected. */
  allowClear?: boolean;
  id?: string;
}

/**
 * A single-choice button group. Buttons rather than a select, because on a
 * phone a row of chips is one tap where a select is three.
 */
export function ChoiceChips<T extends string>({
  label,
  choices,
  value,
  onChange,
  allowClear = true,
  id,
}: ChoiceChipsProps<T>) {
  return (
    <div id={id} className="flex flex-wrap gap-2" role="group" aria-label={label}>
      {choices.map((choice) => {
        const selected = value === choice.value;
        return (
          <button
            key={choice.value}
            type="button"
            aria-pressed={selected}
            title={choice.hint}
            onClick={() => onChange(selected && allowClear ? '' : choice.value)}
            className="jm-chip"
          >
            {choice.icon ? <span aria-hidden="true">{choice.icon}</span> : null}
            {choice.label}
          </button>
        );
      })}
    </div>
  );
}
