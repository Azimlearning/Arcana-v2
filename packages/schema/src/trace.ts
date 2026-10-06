// The turn trace: what each agent did during one chat turn. It makes a multi-agent request
// auditable end to end. Served by GET /turns/{turnId}/trace; it is data about a turn, never content
// the user reads as an answer.

/** Every role in the roster (D-22). Closed on purpose: a new agent is a schema change. */
export type AgentName =
  | "orchestrator"
  | "research"
  | "graph"
  | "fact_checker"
  | "composer"
  | "tutor"
  | "writer"
  | "lab_builder";

/**
 * How one step ended.
 *   ok       the agent finished;
 *   partial  it returned something usable but incomplete;
 *   failed   it raised or could not run;
 *   refused  route_to_agent declined the hop (budget spent, unknown agent, or a loop).
 */
export type StepStatus = "ok" | "partial" | "failed" | "refused";

/** How the whole turn ended: an answer, no evidence to answer from, or an error. */
export type TurnOutcome = "answered" | "empty" | "error";

export interface AgentStep {
  /** Order of the step within the turn, from 0. */
  /** @int */
  hop: number;
  agent: AgentName;
  status: StepStatus;
  /** Tokens this step spent on model calls. */
  /** @int */
  tokens: number;
  /** @int */
  latencyMs: number;
  /** A short reason for a non-ok status, e.g. "hop budget reached". Never an exception message. */
  note: string | null;
}

export interface TurnTrace {
  turnId: string;
  steps: AgentStep[];
  /** @int */
  hopsUsed: number;
  /** @int */
  tokensUsed: number;
  outcome: TurnOutcome;
}
