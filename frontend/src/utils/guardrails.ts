/**
 * Reading the guardrail trail the API returns.
 *
 * `TripPlanResponse.guardrails` is an ordered list of decision records, one
 * per check that ran - input, prompt injection, PII, tool and output. Each
 * record carries at least a `stage` and an `allowed` flag; the rest of the
 * shape differs per stage, which is why the API types it loosely. These
 * helpers are the only place that interprets it.
 */

export interface GuardrailRecord {
  stage?: string;
  allowed?: boolean;
  rule?: string | null;
  reason?: string | null;
  reason_code?: string | null;
  message?: string | null;
  tool?: string | null;
  agent?: string | null;
  warnings?: string[];
  redactions?: string[];
  injection_score?: number;
  matched_rules?: string[];
  [key: string]: unknown;
}

export interface GuardrailSummary {
  /** False when any recorded check refused. */
  passed: boolean;
  /** How many checks ran in total. */
  total: number;
  /** The records that refused, in the order they were decided. */
  blocked: GuardrailRecord[];
  /** Non-blocking notes worth surfacing. */
  warnings: string[];
  records: GuardrailRecord[];
}

export function summariseGuardrails(records: unknown[] | undefined | null): GuardrailSummary {
  const list = (records ?? []) as GuardrailRecord[];
  const blocked = list.filter((record) => record.allowed === false);
  const warnings = list.flatMap((record) =>
    Array.isArray(record.warnings) ? record.warnings : [],
  );

  return {
    passed: blocked.length === 0,
    total: list.length,
    blocked,
    warnings,
    records: list,
  };
}

/** A short, human-readable label for one decision record. */
export function guardrailLabel(record: GuardrailRecord): string {
  const stage = record.stage ?? 'guardrail';
  if (record.tool) return `${stage} · ${record.tool}`;
  if (record.rule) return `${stage} · ${record.rule}`;
  return stage;
}

/** The reason a record gives, whichever field it used. */
export function guardrailReason(record: GuardrailRecord): string | null {
  return record.reason ?? record.message ?? record.reason_code ?? null;
}
