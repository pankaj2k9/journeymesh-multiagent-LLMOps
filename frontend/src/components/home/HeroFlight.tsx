import { useEffect, useRef, useState, type PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { SHOWCASE_ROUTES, cityCode } from '../../utils/cities';

interface HeroFlightProps {
  /** The route the traveller has picked; empty strings fall back to a showcase. */
  origin?: string;
  destination?: string;
}

const SHOWCASE_INTERVAL_MS = 4200;

// Pointer position becomes a gentle tilt, capped so text stays legible.
const MAX_TILT_DEG = 7;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

/**
 * The home page hero: a tilted card with a plane flying an arc between two
 * cities. It shows the traveller's own route as soon as they pick one, and
 * cycles through example routes until then.
 *
 * The flight is SVG `animateMotion`, which CSS `prefers-reduced-motion`
 * cannot stop, so reduced motion is honoured here by rendering the plane
 * parked mid-route instead.
 */
export function HeroFlight({ origin = '', destination = '' }: HeroFlightProps) {
  const { t } = useTranslation();
  const sceneRef = useRef<HTMLDivElement>(null);
  const [showcase, setShowcase] = useState(0);
  const [still] = useState(prefersReducedMotion);

  const picked = Boolean(origin.trim() && destination.trim());

  useEffect(() => {
    if (picked || still) return undefined;
    const timer = window.setInterval(
      () => setShowcase((index) => (index + 1) % SHOWCASE_ROUTES.length),
      SHOWCASE_INTERVAL_MS,
    );
    return () => window.clearInterval(timer);
  }, [picked, still]);

  const [from, to] = picked ? [origin.trim(), destination.trim()] : SHOWCASE_ROUTES[showcase];

  const tilt = (event: PointerEvent<HTMLDivElement>) => {
    const scene = sceneRef.current;
    if (!scene || still) return;
    const box = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - box.left) / box.width - 0.5;
    const y = (event.clientY - box.top) / box.height - 0.5;
    scene.style.setProperty('--jm-tilt-x', `${(-y * MAX_TILT_DEG).toFixed(2)}deg`);
    scene.style.setProperty('--jm-tilt-y', `${(x * MAX_TILT_DEG).toFixed(2)}deg`);
  };

  const reset = () => {
    sceneRef.current?.style.removeProperty('--jm-tilt-x');
    sceneRef.current?.style.removeProperty('--jm-tilt-y');
  };

  // One arc for both the drawn route and the plane's path.
  const route = 'M 70 190 C 170 40, 330 40, 430 150';

  return (
    <div className="relative" onPointerMove={tilt} onPointerLeave={reset} data-testid="hero-flight">
      <div ref={sceneRef} className="jm-hero-scene">
        <svg
          viewBox="0 0 500 260"
          className="h-auto w-full"
          role="img"
          aria-label={t('home.heroRouteLabel', { from, to })}
        >
          {/* A globe's worth of meridians, flattened into the card. */}
          <g className="jm-hero-grid" fill="none" strokeWidth="1">
            <ellipse cx="250" cy="300" rx="320" ry="150" />
            <ellipse cx="250" cy="300" rx="240" ry="110" />
            <ellipse cx="250" cy="300" rx="160" ry="72" />
            <path d="M 250 150 L 250 300 M 90 170 L 180 300 M 410 170 L 320 300" />
          </g>

          <path
            d={route}
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            className="jm-hero-route-glow"
          />
          <path
            key={`${from}-${to}`}
            id="jm-hero-route"
            d={route}
            fill="none"
            strokeWidth="2.5"
            strokeLinecap="round"
            className="jm-hero-route"
          />

          {/* Origin and destination pins, each with a pulse. */}
          <circle cx="70" cy="190" r="10" className="jm-hero-pulse" />
          <circle cx="70" cy="190" r="6" className="jm-hero-pin" />
          <circle cx="430" cy="150" r="10" className="jm-hero-pulse" />
          <circle cx="430" cy="150" r="6" className="jm-hero-pin" />

          <g className="jm-hero-plane">
            {/* Nose points along +x so `rotate="auto"` banks it with the arc. */}
            <path d="M 16 0 L -6 -4 L -10 -14 L -14 -14 L -11 -3 L -18 -2 L -21 -7 L -24 -7 L -22 0 L -24 7 L -21 7 L -18 2 L -11 3 L -14 14 L -10 14 L -6 4 Z" />
            {still ? (
              <animateMotion
                dur="1ms"
                fill="freeze"
                rotate="auto"
                keyPoints="0.55;0.55"
                keyTimes="0;1"
                calcMode="linear"
              >
                <mpath href="#jm-hero-route" />
              </animateMotion>
            ) : (
              <animateMotion
                key={`${from}-${to}`}
                dur="4s"
                repeatCount="indefinite"
                rotate="auto"
                calcMode="spline"
                keyPoints="0;1"
                keyTimes="0;1"
                keySplines="0.45 0 0.25 1"
              >
                <mpath href="#jm-hero-route" />
              </animateMotion>
            )}
          </g>

          <text x="70" y="228" textAnchor="middle" className="fill-ink text-[22px] font-semibold">
            {cityCode(from)}
          </text>
          <text x="70" y="248" textAnchor="middle" className="fill-muted text-[12px]">
            {from}
          </text>
          <text x="430" y="188" textAnchor="middle" className="fill-ink text-[22px] font-semibold">
            {cityCode(to)}
          </text>
          <text x="430" y="208" textAnchor="middle" className="fill-muted text-[12px]">
            {to}
          </text>
        </svg>
      </div>

      {/* Floating cards: what the crew is doing, for texture rather than data. */}
      <div className="pointer-events-none absolute left-2 top-2 hidden sm:block">
        <span className="jm-float inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/90 px-3 py-1 text-xs font-medium text-ink shadow-card backdrop-blur">
          <span aria-hidden="true">✈︎</span> {t('home.heroChipFlights')}
        </span>
      </div>
      <div className="pointer-events-none absolute bottom-3 right-2 hidden sm:block">
        <span className="jm-float-slow inline-flex items-center gap-1.5 rounded-full border border-line bg-surface/90 px-3 py-1 text-xs font-medium text-ink shadow-card backdrop-blur">
          <span aria-hidden="true">🏨</span> {t('home.heroChipStays')}
        </span>
      </div>
    </div>
  );
}
