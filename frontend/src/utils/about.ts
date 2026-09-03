/**
 * Configuration for the About page.
 *
 * Every entry here corresponds to something that actually exists in this
 * repository. Nothing is aspirational: if a technology is listed, it is a
 * dependency or a committed configuration file, and if a capability is
 * described, there is code and a test behind it.
 */

export interface FlowStep {
  id: string;
  icon: string;
}

/** The path a request takes, end to end. */
export const FLOW_STEPS: FlowStep[] = [
  { id: 'request', icon: '\u{1F4AC}' },
  { id: 'guardrails', icon: '\u{1F6E1}\u{FE0F}' },
  { id: 'supervisor', icon: '\u{1F9ED}' },
  { id: 'agents', icon: '\u{1F91D}' },
  { id: 'tools', icon: '\u{1F517}' },
  { id: 'draft', icon: '\u{1F4DD}' },
  { id: 'review', icon: '\u{1F441}\u{FE0F}' },
  { id: 'final', icon: '\u{2705}' },
];

export interface Capability {
  id: string;
  icon: string;
}

export const CAPABILITIES: Capability[] = [
  { id: 'orchestration', icon: '\u{1F9E9}' },
  { id: 'hitl', icon: '\u{1F464}' },
  { id: 'routing', icon: '\u{1F500}' },
  { id: 'data', icon: '\u{1F30D}' },
  { id: 'guardrails', icon: '\u{1F6E1}\u{FE0F}' },
  { id: 'stateful', icon: '\u{1F4BE}' },
  { id: 'observability', icon: '\u{1F4CA}' },
  { id: 'api', icon: '\u{26A1}' },
];

export interface StackGroup {
  id: string;
  items: string[];
}

/**
 * The stack as the repository actually is: React with Vite rather than
 * Next.js, PostgreSQL everywhere, Docker Compose locally and a
 * self-hosted OVHcloud VPS in production.
 */
export const STACK: StackGroup[] = [
  {
    id: 'frontend',
    items: ['React 18', 'TypeScript', 'Vite', 'React Router', 'TanStack Query', 'Tailwind CSS', 'i18next'],
  },
  { id: 'backend', items: ['Python', 'FastAPI', 'Pydantic v2', 'Uvicorn'] },
  { id: 'ai', items: ['LangGraph', 'LangChain', 'Groq'] },
  { id: 'tools', items: ['Model Context Protocol', 'Tavily', 'AviationStack', 'OpenWeather'] },
  { id: 'data', items: ['PostgreSQL', 'SQLAlchemy 2.0', 'Alembic'] },
  { id: 'observability', items: ['LangSmith', 'Structured logging'] },
  {
    id: 'infrastructure',
    items: [
      'Docker',
      'Docker Compose (local)',
      'OVHcloud VPS (production)',
      'Caddy (TLS)',
      'GitHub Actions',
    ],
  },
];

/** Concepts this project demonstrates, all of them implemented. */
export const ENGINEERING_TOPICS: string[] = [
  'multiAgent',
  'langgraph',
  'stateful',
  'hitl',
  'tools',
  'mcp',
  'guardrails',
  'apis',
  'persistence',
  'observability',
  'docker',
  'compose',
  'vps',
  'cicd',
];
