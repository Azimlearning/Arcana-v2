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
  | "studio"
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

/**
 * Why the Composer did or did not show a component, as a short code. Closed on purpose, like the error codes: a code is
 * never an exception message or any text from a document or the question, and a new code is a schema change.
 *   no_grounded_answer     the Research agent produced nothing that could be cited (the answer is shown as "nothing found");
 *   no_ready_document      there is no stored document that is ready;
 *   no_graph_result        the Graph agent did not run or returned nothing;
 *   no_grounded_edge       no relation had a quote naming both of its concepts;
 *   no_shared_entities     fewer than two documents share two or more entities with evidence;
 *   not_a_path             the question's entities were not joined by a path;
 *   single_hop             the path has one hop, which is a graph view and not a path map;
 *   path_too_long          the path has more hops than a map shows;
 *   broken_path            the path's hops do not join up;
 *   ungrounded_hop         a hop on the path had no quote naming both of its concepts;
 *   repeated_concept       the path passes through a concept twice;
 *   nothing_resolved       the question resolved to no concept in the graph, so the search followed nothing;
 *   no_edge_followed       the search followed no edge that led to a passage it returned;
 *   too_many_seeds         the question resolved to more concepts than a traversal view shows (it would no longer be the whole search);
 *   no_grounded_draft      the Studio agent produced no draft section that stood on a verified quote (nothing was drafted, or the Fact Checker removed it all);
 *   no_study_material      the vault held nothing citable to make a study set from for what was asked;
 *   block_failed_validation the block was built but failed server validation, so it was not sent;
 *   answer_unavailable     the answer could not be produced or checked (the turn's error is on the answer block);
 *   not_considered         the turn ended before the Composer could consider this component;
 *   unspecified            a reason this version of the schema has no code for.
 */
export type DecisionReason =
  | "no_grounded_answer"
  | "no_ready_document"
  | "no_graph_result"
  | "no_grounded_edge"
  | "no_shared_entities"
  | "not_a_path"
  | "single_hop"
  | "path_too_long"
  | "broken_path"
  | "ungrounded_hop"
  | "repeated_concept"
  | "nothing_resolved"
  | "no_edge_followed"
  | "too_many_seeds"
  | "no_grounded_draft"
  | "no_study_material"
  | "block_failed_validation"
  | "answer_unavailable"
  | "not_considered"
  | "unspecified";

/** What the Composer decided for one catalog component on one turn. */
export interface ComponentDecision {
  /** The component's block type, for example "GraphView". */
  component: string;
  /** True if a block of this component was sent in a ready or empty state. */
  offered: boolean;
  /** Why not (or, for an empty answer, why it is empty). Empty when it was offered with nothing to explain. */
  reasons: DecisionReason[];
}

export interface TurnTrace {
  turnId: string;
  steps: AgentStep[];
  /** @int */
  hopsUsed: number;
  /** @int */
  tokensUsed: number;
  outcome: TurnOutcome;
  /** One decision per catalog component the Composer considered, in catalog order. */
  composition: ComponentDecision[];
}
