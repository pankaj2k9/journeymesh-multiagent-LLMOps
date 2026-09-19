import { inputClass } from './Field';

interface StepperProps {
  id: string;
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
  decreaseLabel: string;
  increaseLabel: string;
}

/** A number with − and + buttons: one tap per person rather than typing. */
export function Stepper({
  id,
  value,
  min,
  max,
  onChange,
  decreaseLabel,
  increaseLabel,
}: StepperProps) {
  const clamp = (next: number) => Math.min(max, Math.max(min, next));
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        className="jm-chip h-9 w-9 justify-center p-0"
        aria-label={decreaseLabel}
        disabled={value <= min}
        onClick={() => onChange(clamp(value - 1))}
      >
        −
      </button>
      <input
        id={id}
        type="number"
        min={min}
        max={max}
        className={`${inputClass} w-16 text-center`}
        value={value}
        onChange={(event) => onChange(clamp(Number(event.target.value) || min))}
      />
      <button
        type="button"
        className="jm-chip h-9 w-9 justify-center p-0"
        aria-label={increaseLabel}
        disabled={value >= max}
        onClick={() => onChange(clamp(value + 1))}
      >
        +
      </button>
    </div>
  );
}
