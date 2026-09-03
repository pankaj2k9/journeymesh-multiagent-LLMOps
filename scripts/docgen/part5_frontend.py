"""The React frontend: routing, data fetching, i18n, theming, components."""

from __future__ import annotations

from docgen.builder import Guide
from docgen.repo import FACTS


def write(g: Guide) -> None:
    _overview(g)
    _data_layer(g)
    _interaction(g)
    _i18n(g)
    _theme(g)
    _components(g)
    _node_packages(g)


# ---------------------------------------------------------------------------
def _overview(g: Guide) -> None:
    g.h1("The React Application", page_break=True)

    g.p(
        f"The interface is {FACTS.frontend_files} TypeScript and TSX modules built "
        "with Vite. It holds no business rules and no secrets: it renders what the API "
        "returns, and every variable it can see is safe to publish."
    )

    g.h2("The stack, and why each piece is there")
    g.table(
        ["Choice", "Why", "Alternative rejected"],
        [
            ["React 18 + TypeScript",
             "The interface is a set of independent panels over one server response; "
             "types make the API contract checkable at compile time",
             "Plain JavaScript - the response shape is too rich to keep in one's "
             "head"],
            ["Vite",
             "Instant dev server start, native ES modules, one command for a "
             "production build",
             "Create React App - unmaintained and slow to start"],
            ["React Router",
             "Deep-linkable journeys: /trip/{id} is a real URL a traveller can share "
             "or bookmark",
             "A single-page state machine - loses the back button and shareable "
             "links"],
            ["TanStack Query",
             "Server state has different rules from UI state: caching, staleness, "
             "background refetch, request de-duplication",
             "useEffect plus useState - re-implements caching badly in every "
             "component"],
            ["Tailwind CSS",
             "Semantic design tokens defined once, used everywhere; theming becomes "
             "one CSS variable swap",
             "CSS modules - would need a parallel dark palette in every file"],
            ["i18next",
             "Mature runtime translation with namespaces and interpolation",
             "Hand-rolled dictionary lookups - loses pluralisation and fallbacks"],
        ],
        caption="The frontend stack and the reasoning behind each choice.",
        widths=[1.2, 2.4, 2.2],
    )

    g.h2("Directory layout")
    g.code(
        """
frontend/src
  api/          client.ts, trips.ts, reviews.ts     - the only place fetch() appears
  components/
    common/     Button, Card, Badge, Callout, Skeleton, Spinner, EmptyState,
                SourceBadge, ThemeToggle, ThemeSelector
    language/   LanguageSelector
    layout/     Header, Footer, Layout
    planner/    PlannerForm, Field, InterestPicker, TravelStylePicker,
                PlanningProgress
    review/     ReviewPanel, RequestChangesForm
    trip/       JourneyOverviewCard, FlightsSection, HotelsSection,
                WeatherSection, BudgetSection, ItinerarySection,
                EvaluationPanel, ProviderStatusPanel, StatusBadge, TravelTips
  hooks/        useTrips.ts, useLanguage.ts
  i18n/         config.ts
  locales/      en, bn, hi
  pages/        HomePage, TripPage, HistoryPage, SettingsPage, AboutPage,
                NotFoundPage
  theme/        theme.ts, ThemeProvider.tsx, useTheme.ts, index.ts
  types/        index.ts     - the TypeScript mirror of the API response
  utils/        format.ts, constants.ts, session.ts
  test/         seven test files
""",
        caption="Listing. The frontend source tree.",
    )

    g.h2("Routes")
    g.table(
        ["Path", "Page", "Purpose"],
        [
            ["`/`", "HomePage", "The planner form and the entry point"],
            ["`/trip/:tripId`", "TripPage",
             "One journey: results, provider labels, scores, review panel"],
            ["`/history`", "HistoryPage", "Journeys from this browser session"],
            ["`/settings`", "SettingsPage", "Language and theme"],
            ["`/about`", "AboutPage", "What the system is and how it works"],
            ["`*`", "NotFoundPage", "Anything else"],
        ],
        caption="Client-side routes. Each is served by the SPA fallback in "
                "app/api/static_site.py.",
        widths=[1.2, 1.2, 3.4],
    )

    g.h2("Sessions without accounts")
    g.p(
        "There are no user accounts. utils/session.ts generates an opaque identifier "
        "the first time the application loads, stores it in the browser, and sends it "
        "with every request. The server scopes journeys to it. This gives a traveller "
        "a history without asking for a password, and it means the database holds no "
        "credentials to leak."
    )
    g.callout(
        "note",
        "The trade is explicit: a session id in browser storage is not authentication. "
        "Anyone holding it can read those journeys. That is acceptable for a system "
        "that stores travel drafts and no personal identifiers, and it is why the PII "
        "guard works to keep personal identifiers out in the first place.",
    )


# ---------------------------------------------------------------------------
def _data_layer(g: Guide) -> None:
    g.h1("Data Fetching with TanStack Query", page_break=True)

    g.h2("Server state is not UI state")
    g.definition(
        "Server state",
        "Data that is owned by a remote system, may change without the client's "
        "knowledge, is shared between components, and requires caching, invalidation "
        "and staleness policy to use correctly.",
        "Anything that lives on the server. Your app only ever holds a copy, and the "
        "hard part is knowing when the copy went out of date.",
    )
    g.p(
        "Handling server state with useEffect and useState means re-implementing "
        "caching, de-duplication, retry and invalidation in every component, slightly "
        "differently each time. TanStack Query provides one implementation with an "
        "explicit policy."
    )

    g.table(
        ["Problem", "Without a query library", "With TanStack Query"],
        [
            ["Two components need the same trip",
             "Two fetches, two copies, two loading states",
             "One cache entry keyed by trip id"],
            ["The user navigates away and back",
             "Refetch from scratch, blank screen",
             "Cached data renders instantly, refreshed in the background"],
            ["A revision changes the trip",
             "Manual state surgery in every component that holds it",
             "Invalidate the key; every consumer re-renders"],
            ["A request fails",
             "Hand-written retry in each component",
             "One retry policy, one error state"],
        ],
        caption="What the query layer removes from component code.",
        widths=[1.4, 2.2, 2.2],
    )

    g.h2("The hooks")
    g.p(
        "hooks/useTrips.ts is the only module components use to reach the API. It "
        "exposes queries for listing and fetching journeys and mutations for planning, "
        "approving, requesting changes, regenerating and deleting. Mutations invalidate "
        "the affected keys on success, so the review panel does not need to know what "
        "else on the page is showing trip data."
    )
    g.code(
        """
// Shape of the data layer (frontend/src/hooks/useTrips.ts)

useTripsQuery(sessionId)     -> GET  /api/v1/trips
useTripQuery(tripId)         -> GET  /api/v1/trips/{id}
usePlanTrip()                -> POST /api/v1/trips/plan
useApproveTrip(tripId)       -> POST /api/v1/trips/{id}/approve
useRequestChanges(tripId)    -> POST /api/v1/trips/{id}/request-changes
useRegenerateTrip(tripId)    -> POST /api/v1/trips/{id}/regenerate
useDeleteTrip(tripId)        -> DELETE /api/v1/trips/{id}

// Every mutation invalidates ["trip", tripId] and ["trips", sessionId]
// on success, so no component has to reconcile state by hand.
""",
        caption="Listing. The data layer's public surface.",
    )

    g.h2("One place for fetch()")
    g.p(
        "api/client.ts is the only module that calls fetch. It attaches the session "
        "id, sets the content type, parses errors into a typed error object and applies "
        "the base URL. A component that wanted to talk to the API directly would have "
        "to duplicate all of that, which is the point: the friction is the "
        "architecture."
    )

    g.understand([
        "Why server state needs different machinery from component state.",
        "What invalidating a query key does that manual state updates do not.",
        "Why exactly one module in the frontend is allowed to call fetch.",
    ])


# ---------------------------------------------------------------------------
def _interaction(g: Guide) -> None:
    g.h1("Interaction and Feedback", page_break=True)

    g.h2("Every long-running action reports the same way")
    g.p(
        "Planning, approving and revising all call a model and one or more "
        "providers, so all three follow one pattern: the button that started the "
        "work carries the spinner, it disables itself to stop a duplicate "
        "submission, and it disables the other decision so a slow revision cannot "
        "be approved out from under itself. The spinner lives in the Button "
        "primitive, so no screen re-implements it."
    )
    g.table(
        ["Action", "Button", "While it runs"],
        [
            ["Plan a journey", "Plan my journey",
             "Spinner in the button; the quick-prompt chips are disabled"],
            ["Approve", "Approve & Generate Final",
             "Spinner in the button; Revise is disabled; the plan below is dimmed "
             "and marked aria-busy"],
            ["Revise", "Revise Using Feedback",
             "Spinner in the button; Approve and the feedback box are disabled"],
        ],
        caption="The three long-running actions and what each one does to the "
                "interface.",
        widths=[1.1, 1.6, 3.1],
    )

    g.h2("A spinner that always stops")
    g.p(
        "A request that never answers would leave a spinner turning for ever, so "
        "the API client applies its own timeout - generous, because a planning run "
        "does real work - and converts an abandoned request into an ordinary "
        "failure the interface can report. Every failure then goes through one "
        "describer, so a timeout reads the same wherever it happened."
    )
    g.table(
        ["Failure", "What the traveller sees", "Retry offered"],
        [
            ["Timeout", "The service took too long; nothing was lost", "Yes"],
            ["Network unreachable", "JourneyMesh could not reach the service", "Yes"],
            ["Rate limited", "Too many requests for now", "Yes"],
            ["Server error", "The service ran into a problem", "Yes"],
            ["Revision limit", "No further changes can be made", "No"],
            ["Not found", "That journey does not exist for this session", "No"],
        ],
        caption="Error states, from utils/apiError.ts.",
        widths=[1.2, 3.0, 1.0],
    )

    g.h2("Details are collapsed until they are asked for")
    g.p(
        "Trip details on the planner, the guardrail trail and execution notes on "
        "the execution plan, and the evaluation and provider panels on the trip "
        "page all start closed behind a Show details button that becomes Hide "
        "details. The summary - what was planned, which agents ran, whether the "
        "guardrails passed - is always visible; the technical record is one click "
        "away and never opens itself."
    )

    g.h2("Taking the plan away")
    g.p(
        "Copy and Download render the journey through one function, so the "
        "clipboard and the file cannot disagree, and provenance labels travel with "
        "the figures. Save as PDF opens the browser's own print dialogue against a "
        "print stylesheet that drops the navigation and the controls and forces a "
        "light ground - a real PDF, and no PDF library in the bundle."
    )


# ---------------------------------------------------------------------------
def _i18n(g: Guide) -> None:
    g.h1("Internationalisation in the Interface", page_break=True)

    g.p(
        f"The English catalogue contains {FACTS.locale_keys} keys, and Bengali and "
        "Hindi mirror it. Every string a traveller can see comes from the catalogue; "
        "there is a test that fails if a locale is missing a key that English defines."
    )

    g.table(
        ["Concern", "How it is handled"],
        [
            ["Selecting a language",
             "LanguageSelector writes to the i18next instance and persists the choice "
             "under `journeymesh_language`"],
            ["Detecting a language",
             "i18next-browser-languagedetector reads the stored choice first, then the "
             "browser preference, then falls back to English"],
            ["Server-rendered content",
             "The chosen language is sent with the request; the final response agent "
             "renders through the server catalogue"],
            ["Missing keys",
             "English is the fallback language, and a test asserts catalogue parity "
             "so a missing key fails CI rather than reaching a traveller"],
        ],
        caption="The four internationalisation concerns and their answers.",
        widths=[1.4, 4.4],
    )

    g.h2("Two catalogues, one language choice")
    g.p(
        "There are deliberately two translation catalogues: one in the frontend for "
        "interface chrome - labels, buttons, headings, empty states - and one in the "
        "backend for content the agents produce. They are separate because they change "
        "for different reasons and are edited by different work. The traveller's "
        "language choice drives both."
    )

    g.h2("Formatting")
    g.p(
        "utils/format.ts handles dates, currency and numbers. Formatting is locale-"
        "aware through the platform's Intl APIs rather than by string concatenation, "
        "so a price renders correctly in each language without a separate code path."
    )


# ---------------------------------------------------------------------------
def _theme(g: Guide) -> None:
    g.h1("Light and Dark Mode", page_break=True)

    g.p(
        "JourneyMesh has two themes, light and dark, with light as the default. The "
        "dark theme is a designed palette rather than an inversion of the light one: "
        "inverting a light theme produces glaring whites on near-black and washes out "
        "every status colour."
    )

    g.h2("Semantic tokens")
    g.p(
        "No component names a literal colour. Components say `bg-surface`, "
        "`text-muted`, `border-line`, `text-positive-fg`. Each token resolves to a CSS "
        "custom property defined twice in src/index.css - once on `:root` for light and "
        "once under `.dark` for dark - so a component is written once and themed "
        "centrally."
    )
    g.code(
        """
/* tailwind.config.js */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas:  'rgb(var(--jm-canvas) / <alpha-value>)',
        surface: 'rgb(var(--jm-surface) / <alpha-value>)',
        ink:     'rgb(var(--jm-ink) / <alpha-value>)',
        muted:   'rgb(var(--jm-muted) / <alpha-value>)',
        positive: {
          fg:   'rgb(var(--jm-positive-fg) / <alpha-value>)',
          bg:   'rgb(var(--jm-positive-bg) / <alpha-value>)',
          line: 'rgb(var(--jm-positive-line) / <alpha-value>)',
        },
        /* caution, negative, info, neutral, brand follow the same shape */
      },
    },
  },
};
""",
        caption="Listing. Semantic tokens mapped to CSS variables. `<alpha-value>` "
                "keeps Tailwind's opacity modifiers working, so `bg-surface/60` is "
                "still valid.",
    )

    g.table(
        ["Token family", "Members", "Used for"],
        [
            ["Surfaces", "`canvas`, `surface`, `elevated`, `line`, `line-strong`",
             "Page ground, cards, raised panels, borders"],
            ["Text", "`ink`, `muted`, `faint`",
             "Primary, secondary and tertiary text"],
            ["Brand", "`accent`, `accent-strong`, `accent-soft`, `accent-contrast`",
             "Primary actions and emphasis"],
            ["Status", "`positive`, `caution`, `negative`, `info`, `neutral`, "
                       "`brand`, each with `-fg`, `-bg`, `-line`",
             "Budget status, provenance badges, guardrail outcomes, callouts"],
        ],
        caption="The semantic token families defined in src/index.css.",
        widths=[1.0, 2.6, 2.2],
    )

    g.h2("Contrast")
    g.p(
        "Both palettes were checked against WCAG contrast ratios and the measured "
        "values are recorded as comments beside the tokens: primary text reaches "
        "14.9:1 on surface in light and 14.2:1 in dark, secondary text 5.9:1 and 7.4:1, "
        "and the tertiary tone - used sparingly - 4.6:1 and 5.2:1. Status colours have "
        "separate foreground, background and line values in each theme rather than one "
        "colour used at different opacities."
    )

    g.h2("Preventing the flash")
    g.p(
        "If the theme were applied by React after hydration, a dark-mode user would see "
        "a white flash on every page load. A small script inlined into index.html runs "
        "before the first paint: it reads the stored preference, toggles the `dark` "
        "class on the document element, sets `color-scheme` so native controls match, "
        "and updates the theme-colour meta tag."
    )
    g.code(
        """
// frontend/src/theme/theme.ts
export const THEME_INIT_SCRIPT =
  `(function(){try{` +
  `var k='journeymesh_theme';` +
  `var s=window.localStorage.getItem(k);` +
  `var d=s==='dark';` +
  `var e=document.documentElement;` +
  `e.classList.toggle('dark',d);` +
  `e.style.colorScheme=d?'dark':'light';` +
  `e.dataset.theme=d?'dark':'light';` +
  `var m=document.querySelector('meta[name="theme-color"]');` +
  `if(m)m.setAttribute('content',d?'#090e17':'#f7f5f0');` +
  `}catch(e){}})();`;
""",
        caption="Listing. The pre-paint theme initialiser, shown with its "
                "concatenation expanded for readability.",
    )
    g.callout(
        "important",
        "An inline script is normally forbidden by the content security policy. Rather "
        "than weaken the policy with 'unsafe-inline', the exact SHA-256 hash of this "
        "script is allowlisted in both backend/app/security/headers.py and "
        "frontend/nginx.conf. Changing the script by even one character therefore "
        "requires regenerating the hash in both places - which is the intended friction.",
    )

    g.h2("The API surface")
    g.table(
        ["Export", "File", "Purpose"],
        [
            ["`Theme`", "`theme/theme.ts`", "The literal type `'light' | 'dark'`"],
            ["`DEFAULT_THEME`", "`theme/theme.ts`", "`'light'`"],
            ["`THEME_STORAGE_KEY`", "`theme/theme.ts`", "`'journeymesh_theme'`"],
            ["`applyTheme()`", "`theme/theme.ts`",
             "Applies a theme to the document element"],
            ["`oppositeTheme()`", "`theme/theme.ts`", "The other one"],
            ["`ThemeProvider`", "`theme/ThemeProvider.tsx`",
             "Holds the theme, persists it, applies it"],
            ["`useTheme()`", "`theme/useTheme.ts`",
             "`{ theme, setTheme, toggleTheme }`"],
            ["`ThemeToggle`", "`components/common/ThemeToggle.tsx`",
             "The sun/moon button in the navigation bar"],
            ["`ThemeSelector`", "`components/common/ThemeSelector.tsx`",
             "A two-option radio group on the settings page"],
        ],
        caption="The theme module's public surface.",
        widths=[1.4, 1.8, 2.6],
    )

    g.h2("Accessibility")
    g.bullets([
        "ThemeToggle is a button with an accessible name and `aria-pressed`, so a "
        "screen reader announces both what it does and its current state.",
        "ThemeSelector is a proper radiogroup with two radio options rather than a "
        "pair of styled buttons.",
        "`color-scheme` is set on the document element, so native form controls, "
        "scrollbars and the browser's own chrome match the chosen theme.",
        "The theme is exposed as `data-theme` on the document element, which is what "
        "the tests assert against and what any future CSS can key off.",
    ])

    g.callout(
        "note",
        "There is no system-following third option. It was considered and removed: "
        "with only two states, an explicit choice that persists is simpler to reason "
        "about, simpler to test, and removes a class of confusing behaviour where the "
        "interface changes appearance because the operating system crossed sunset.",
    )

    g.understand([
        "Why the dark palette is designed rather than inverted.",
        "How a semantic token turns into a colour in each theme.",
        "Why an inline script is required to prevent the flash, and how the CSP still "
        "forbids every other inline script.",
        "Why theme and language are stored separately and never affect each other.",
    ])


# ---------------------------------------------------------------------------
def _components(g: Guide) -> None:
    g.h1("Component Reference", page_break=True)

    g.h2("Common")
    g.table(
        ["Component", "Purpose"],
        [
            ["`Button`", "The single button primitive; variants are props, not "
                         "classes copied between files"],
            ["`Card`", "The surface every panel sits on"],
            ["`Badge`", "A small status pill built from the status token families"],
            ["`Callout`", "An inline note, caution or tip"],
            ["`Skeleton`", "Loading placeholder, themed by `.jm-skeleton`"],
            ["`Spinner`", "Indeterminate progress"],
            ["`EmptyState`", "What a panel shows when there is nothing to show"],
            ["`SourceBadge`", "Renders a provenance label - the visible half of the "
                              "data-honesty story"],
            ["`ThemeToggle`", "Light/dark switch in the navigation bar"],
            ["`ThemeSelector`", "Light/dark radio group on the settings page"],
            ["`Collapsible`", "The one Show details / Hide details disclosure. "
                              "Collapsed by default, and it unmounts its content "
                              "rather than hiding it, so the tab order matches the "
                              "screen"],
        ],
        caption="Common components.",
        widths=[1.3, 4.5],
    )

    g.h2("Planner")
    g.table(
        ["Component", "Purpose"],
        [
            ["`PlannerForm`", "Collects the whole trip request and submits it as one "
                              "structured object"],
            ["`Field`", "A labelled input with error and hint slots, themed by "
                        "`.jm-field`"],
            ["`InterestPicker`", "Multi-select interests"],
            ["`TravelStylePicker`", "Single-select travel style"],
            ["`PlanningProgress`", "Shows which agents are running during a draft"],
            ["`QuickPrompts`", "Example prompts as chips. Fills the box from "
                               "QUICK_PROMPTS; never submits"],
            ["`GuardrailBlockedCard`", "What a refused request looks like, in the "
                                       "place the execution plan would otherwise be"],
        ],
        caption="Planner components.",
        widths=[1.3, 4.5],
    )

    g.h2("Trip")
    g.table(
        ["Component", "Renders"],
        [
            ["`JourneyOverviewCard`", "Origin, destination, dates, travellers, status"],
            ["`FlightsSection`", "`flight_results.options`"],
            ["`HotelsSection`", "`hotel_results.options`"],
            ["`WeatherSection`", "`weather_info.forecast`"],
            ["`BudgetSection`", "`budget_analysis.breakdown` and the budget status"],
            ["`ItinerarySection`", "`itinerary_plan.days`"],
            ["`EvaluationPanel`", "The ten dimension scores and the overall result"],
            ["`ProviderStatusPanel`", "Every external call and its provenance label"],
            ["`StatusBadge`", "The trip and review status"],
            ["`TravelTips`", "Advisory notes produced by the agents"],
            ["`SupervisorPlanCard`", "The execution plan: guardrail status, the "
                                     "supervisor's reasoning and the agents it "
                                     "chose, with the guardrail trail collapsed"],
            ["`AgentChips`", "Selected agents, rendered from AGENT_DISPLAY"],
            ["`PlanActions`", "Draft or final heading, thread id, and Copy, "
                              "Download and Save as PDF"],
        ],
        caption="Trip components, each mapped to the state key it renders.",
        widths=[1.5, 4.3],
    )

    g.h2("Review")
    g.table(
        ["Component", "Purpose"],
        [
            ["`ReviewPanel`", "The approve / request-changes decision, and the "
                              "remaining revision budget"],
            ["`RequestChangesForm`", "The always-visible feedback box and both "
                                     "decisions - approve, or revise using the "
                                     "feedback. Each button carries its own spinner "
                                     "and locks the other while it runs"],
        ],
        caption="Review components.",
        widths=[1.5, 4.3],
    )


# ---------------------------------------------------------------------------
def _node_packages(g: Guide) -> None:
    g.h1("Frontend Dependency Reference", page_break=True)

    reasons = {
        "react": "The view library.",
        "react-dom": "React's browser renderer.",
        "react-router-dom": "Client-side routing and deep links.",
        "@tanstack/react-query": "Server-state cache, invalidation and mutations.",
        "i18next": "Translation runtime.",
        "react-i18next": "React bindings for i18next.",
        "i18next-browser-languagedetector": "Reads the stored or browser language.",
    }
    g.table(
        ["Package", "Version", "Why it is here"],
        [[f"`{n}`", v, reasons.get(n, "See package.json")]
         for n, v in FACTS.node_deps],
        caption="Runtime dependencies, from frontend/package.json.",
        widths=[1.9, 1.0, 2.9],
    )

    dev_reasons = {
        "vite": "Dev server and production bundler.",
        "@vitejs/plugin-react": "React fast refresh and JSX transform for Vite.",
        "typescript": "Type checking; `tsc --noEmit` runs in CI.",
        "vitest": "Test runner, sharing Vite's transform pipeline.",
        "jsdom": "The DOM implementation the tests run against.",
        "@testing-library/react": "Renders components and queries them the way a user "
                                  "would.",
        "@testing-library/jest-dom": "DOM-specific assertions.",
        "@testing-library/user-event": "Realistic user interaction simulation.",
        "tailwindcss": "The utility and token system.",
        "postcss": "The CSS pipeline Tailwind runs in.",
        "autoprefixer": "Vendor prefixes for the browser matrix.",
        "@types/react": "React type definitions.",
        "@types/react-dom": "React DOM type definitions.",
        "@types/node": "Node type definitions, needed by the CSS-reading theme test.",
    }
    g.table(
        ["Package", "Version", "Why it is here"],
        [[f"`{n}`", v, dev_reasons.get(n, "See package.json")]
         for n, v in FACTS.node_dev_deps],
        caption="Development dependencies, from frontend/package.json.",
        widths=[1.9, 1.0, 2.9],
    )

    g.callout(
        "warning",
        "package-lock.json pins the exact tree, including platform-specific optional "
        "binaries such as the Rollup native module. It must be committed and must not "
        "be deleted to resolve an install error - deleting it removes the record of "
        "every platform variant. The correct fix for a mismatched native module is to "
        "remove node_modules and reinstall from the lockfile.",
    )
