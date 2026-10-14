// HTTP and stream shapes that cross the wire. Anything that crosses the wire belongs here.

import type { UIBlock } from "./blocks";
import type { ErrorEnvelope } from "./errors";
import type { LayoutSpec } from "./layout";
import type { Citation, Mastery, PageRef } from "./payloads";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

/**
 * POST /chat body. Single user (D-04), so there is no notebook or user id.
 * The schema has no length bounds; the endpoint enforces them (non-empty message, capped history).
 */
export interface ChatRequest {
  message: string;
  history: ChatMessage[];
}

/** POST /ingest response. The request itself is multipart/form-data and has no schema type. */
export interface IngestResponse {
  docId: string;
  title: string;
  status: "ready" | "failed";
  /** @int */
  chunkCount: number;
  /** Populated when status is "failed". */
  error: string | null;
}

/**
 * GET /workspace response: the workspace as it is before any question (D-28). `layout` is the fixed prebuilt layout and
 * `blocks` the blocks it places (a source list of the stored documents). Validated like every other block and layout.
 */
export interface WorkspaceResponse {
  layout: LayoutSpec;
  blocks: UIBlock[];
}

// ── SSE stream (POST /chat) ─────────────────────────────────────────────────
// Each SSE message carries exactly one StreamEvent as JSON in `data:`.
// A BlockEvent whose block.id was already seen REPLACES that block (upsert by id): this is how a
// block moves loading -> partial -> ready. There is no patch type.

export interface BlockEvent {
  type: "block";
  block: UIBlock;
}

/**
 * Where the turn's blocks go (level 2). Sent after the turn's blocks and before `done`, only if it passed
 * validation; a client that cannot read it keeps the layout it has.
 */
export interface LayoutEvent {
  type: "layout";
  layout: LayoutSpec;
}

/** A failure of the whole turn (as opposed to one block, which carries meta.error). */
export interface StreamErrorEvent {
  type: "error";
  error: ErrorEnvelope;
}

export interface DoneEvent {
  type: "done";
}

export type StreamEvent = BlockEvent | LayoutEvent | StreamErrorEvent | DoneEvent;

// ── The learner layer (M2.7, D-35 A6): POST /learner/events, DELETE /learner ──────────────────────────────────────────

/** How the learner rates their own grasp of a concept. Quiz results join as `quiz_correct` and `quiz_wrong` (P5). */
export type LearnerSignal = "know" | "unsure" | "dont_know";

export interface LearnerEventRequest {
  /** A page of the vault. The server refuses an id it does not hold. */
  pageId: string;
  signal: LearnerSignal;
}

export interface LearnerEventResponse {
  pageId: string;
  /** The page's mastery after this event. */
  mastery: Mastery;
}

// ── The quiz (Q1, D-35 A8): POST /quiz/answer ─────────────────────────────────────────────────────────────────────────

export interface QuizAnswerRequest {
  /** An item id from a `QuizCard`. The server derives the item again and refuses one it cannot. */
  itemId: string;
  /** The page the learner chose, one of the item's four options. */
  chosenId: string;
}

/**
 * The result of one answer. `answer` is the blanked concept and `citation` the sentence it came from, unblanked (id `c1`,
 * verbatim in a stored passage). `mastery` is the blanked concept's mastery after this answer, recorded as `quiz_correct` or
 * `quiz_wrong` for it (never for the page that was chosen).
 */
export interface QuizAnswerResponse {
  itemId: string;
  correct: boolean;
  answer: PageRef;
  citation: Citation;
  mastery: Mastery;
}

// ── Labs (P4, D-36): POST /labs ───────────────────────────────────────────────────────────────────────────────────────

/** Ask the server to make a lab from one of its contracts. The server generates, checks, verifies and answers with a workspace body. */
export interface LabRequest {
  contractId: string;
}

/**
 * One lab the server can make and whether the stored passages support it now (the evidence precondition): `available` is true only if a
 * stored passage states the lab's formula, and then `docTitle` and `page` say where. Otherwise `reason` says why not, in words.
 */
export interface LabSummary {
  contractId: string;
  title: string;
  available: boolean;
  docTitle: string | null;
  /** @int */
  page: number | null;
  reason: string | null;
}

/** GET /labs: every lab the server knows, with whether the documents support it. */
export interface LabList {
  labs: LabSummary[];
}

// ── Vault lint (M2.8, D-35): GET /vault/lint ──────────────────────────────────────────────────────────────────────────

/** A page named in the lint report. */
export interface LintPageRef {
  id: string;
  label: string;
  /** @int */
  passages: number;
}

/**
 * Two pages whose names suggest one concept, awaiting a person's review. Never merged by the system. `reason`: `same_name` (the same
 * words after folding plurals and hyphens), `one_more_word` (one name is the other plus one word) or `initials` (one is the
 * initials of the other).
 */
export type LintDuplicateReason = "same_name" | "one_more_word" | "initials";

export interface LintDuplicate {
  a: LintPageRef;
  b: LintPageRef;
  reason: LintDuplicateReason;
}

/** One paper's definition of a concept, verbatim, with the paper's title. */
export interface LintDefinition {
  docTitle: string;
  text: string;
}

/** A concept that two or more papers define: the definitions side by side, not compared or judged. */
export interface LintTension {
  page: LintPageRef;
  definitions: LintDefinition[];
}

/**
 * What a person should look at in the vault. Reported, never fixed: orphans (no link of either kind), near-duplicate pages, concepts
 * defined in several papers, and hub pages (mentioned in a quarter or more of all passages). Each list is capped at 50 for display;
 * the totals are exact.
 */
export interface VaultLintResponse {
  /** @int */
  pages: number;
  orphans: LintPageRef[];
  /** @int */
  orphansTotal: number;
  duplicates: LintDuplicate[];
  /** @int */
  duplicatesTotal: number;
  tensions: LintTension[];
  /** @int */
  tensionsTotal: number;
  hubs: LintPageRef[];
}
