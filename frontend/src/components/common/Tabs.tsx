import type { ReactNode } from 'react';

export interface TabDefinition {
  id: string;
  label: string;
  /** Rendered beside the label - a count, or a dot for "needs attention". */
  badge?: ReactNode;
}

interface TabsProps {
  tabs: TabDefinition[];
  active: string;
  onChange: (id: string) => void;
  ariaLabel: string;
}

/**
 * A horizontal tab strip that scrolls rather than wraps on a narrow screen.
 *
 * Wrapping ten tabs onto three lines pushes the content off a phone entirely;
 * scrolling keeps the panel where the thumb expects it. Keyboard users get
 * real arrow-key navigation, which is the part a div-based tab strip usually
 * loses.
 */
export function Tabs({ tabs, active, onChange, ariaLabel }: TabsProps) {
  const move = (direction: 1 | -1) => {
    const index = tabs.findIndex((tab) => tab.id === active);
    if (index === -1) return;
    const next = (index + direction + tabs.length) % tabs.length;
    onChange(tabs[next].id);
    document.getElementById(`tab-${tabs[next].id}`)?.focus();
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1"
      onKeyDown={(event) => {
        if (event.key === 'ArrowRight') {
          event.preventDefault();
          move(1);
        } else if (event.key === 'ArrowLeft') {
          event.preventDefault();
          move(-1);
        }
      }}
    >
      {tabs.map((tab) => {
        const selected = tab.id === active;
        return (
          <button
            key={tab.id}
            id={`tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-controls={`panel-${tab.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(tab.id)}
            className={`shrink-0 whitespace-nowrap rounded-xl px-3 py-2 text-sm font-medium transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              selected
                ? 'bg-accent-soft text-accent'
                : 'text-muted hover:bg-elevated hover:text-ink'
            }`}
          >
            <span className="flex items-center gap-1.5">
              {tab.label}
              {tab.badge}
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface TabPanelProps {
  id: string;
  active: string;
  children: ReactNode;
}

export function TabPanel({ id, active, children }: TabPanelProps) {
  if (id !== active) return null;
  return (
    <div id={`panel-${id}`} role="tabpanel" aria-labelledby={`tab-${id}`} tabIndex={0}>
      {children}
    </div>
  );
}
