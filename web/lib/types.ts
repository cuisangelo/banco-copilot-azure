// Mirror of packages/contracts/src/bank_contracts/{models,auth}.py — same names, same shapes.

export type ProductCategory = "account" | "credit_card" | "consumer_loan" | "mortgage";
export type Level2Field = "monthly_income" | "current_debt" | "payment_behavior" | "employment_tenure_months";
export const LEVEL2_FIELDS: readonly Level2Field[] = [
  "monthly_income",
  "current_debt",
  "payment_behavior",
  "employment_tenure_months",
];
export type ChatStatus = "ok" | "clarification" | "insufficient" | "contradiction" | "rejected" | "access_required";
export type AccessRequestStatus = "pending" | "approved" | "partially_approved" | "rejected" | "expired";
export const CUSTOMER_ID_PATTERN = /^C-\d{4}$/;
export const GRANT_MINUTES = 30;

export type Role = "Asesor" | "Supervisor";
export type PersonaKey = "ana" | "bruno" | "sofia";
export const PERSONAS: Record<PersonaKey, { name: string; role: Role }> = {
  ana: { name: "Ana", role: "Asesor" },
  bruno: { name: "Bruno", role: "Asesor" },
  sofia: { name: "Sofía", role: "Supervisor" },
};

export interface AccessRequestCreate {
  customer_id: string;
  fields: Level2Field[];
  purpose: string;
}

export interface AccessRequest extends AccessRequestCreate {
  id: string;
  requested_by: string;
  status: AccessRequestStatus;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  approved_fields: Level2Field[];
}

export interface AccessDecision {
  approved_fields: Level2Field[];
}

export interface Citation {
  id: string;
  kind: "doc" | "product" | "customer";
  ref: string;
  snippet: string;
}

export interface Claim {
  text: string;
  citation_ids: string[];
}

export interface EscalationDraft {
  id: string;
  area: string;
  summary: string;
  evidence: Citation[];
}

export interface EscalationDecision {
  approve: boolean;
}

export interface ChatRequest {
  session_id: string;
  message: string;
  customer_id: string | null;
}

export interface ChatAnswer {
  status: ChatStatus;
  message: string;
  requirements: Claim[];
  steps: Claim[];
  citations: Citation[];
  access_request: AccessRequest | null;
  escalation: EscalationDraft | null;
}

export interface TraceEvent {
  node: string;
  duration_ms: number;
  data: Record<string, unknown>;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface ErrorEvent {
  code: "token_cap" | "rate_limited" | "upstream" | "unauthorized" | "internal";
  message: string;
}

export interface DemoSession {
  token: string;
  name: string;
  role: Role;
}
