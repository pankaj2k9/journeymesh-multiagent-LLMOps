import type { ReactNode } from 'react';

type Tone = 'info' | 'warning' | 'danger' | 'success';

const TONES: Record<Tone, string> = {
  info: 'border-info-line bg-info-bg text-info-fg',
  warning: 'border-caution-line bg-caution-bg text-caution-fg',
  danger: 'border-negative-line bg-negative-bg text-negative-fg',
  success: 'border-positive-line bg-positive-bg text-positive-fg',
};

// Colour is never the only signal: each tone also carries an icon and the
// callout keeps its title, so the meaning survives a greyscale screen.
const ICONS: Record<Tone, string> = {
  info: 'i',
  warning: '!',
  danger: '!',
  success: 'ok',
};

interface CalloutProps {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  actions?: ReactNode;
}

export function Callout({ tone = 'info', title, children, actions }: CalloutProps) {
  return (
    <div className={`rounded-xl border px-4 py-3 text-sm ${TONES[tone]}`} role="status">
      {title ? (
        <p className="flex items-center gap-2 font-semibold">
          <span
            aria-hidden="true"
            className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-current text-[11px] font-bold uppercase"
          >
            {ICONS[tone]}
          </span>
          {title}
        </p>
      ) : null}
      <div className={title ? 'mt-1' : undefined}>{children}</div>
      {actions ? <div className="mt-3 flex flex-wrap gap-2">{actions}</div> : null}
    </div>
  );
}
