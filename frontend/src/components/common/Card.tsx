import type { ReactNode } from 'react';

interface CardProps {
  children: ReactNode;
  className?: string;
}

export function Card({ children, className = '' }: CardProps) {
  return (
    <div
      className={`rounded-2xl border border-slate-200 bg-white shadow-card ${className}`.trim()}
    >
      {children}
    </div>
  );
}

interface SectionProps {
  title: string;
  icon?: ReactNode;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  id?: string;
}

export function Section({ title, icon, description, actions, children, id }: SectionProps) {
  return (
    <section id={id} className="scroll-mt-24">
      <Card>
        <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-semibold text-journey-ink">
              {icon}
              {title}
            </h2>
            {description ? (
              <p className="mt-1 text-sm text-journey-slate">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
        </header>
        <div className="px-5 py-4">{children}</div>
      </Card>
    </section>
  );
}
