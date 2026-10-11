import type { AccessRequestStatus, ChatStatus, Level2Field } from "./types";

export const STATUS_LABEL: Record<ChatStatus, string> = {
  ok: "Respuesta con fuentes",
  clarification: "Falta un dato",
  insufficient: "Sin respaldo suficiente",
  contradiction: "Fuentes en conflicto",
  rejected: "Consulta rechazada",
  access_required: "Requiere acceso a datos",
};

export const FIELD_LABEL: Record<Level2Field, string> = {
  monthly_income: "Renta mensual",
  current_debt: "Deuda vigente",
  payment_behavior: "Comportamiento de pago",
  employment_tenure_months: "Antigüedad laboral",
};

export const REQUEST_STATUS_LABEL: Record<AccessRequestStatus, string> = {
  pending: "Esperando al Supervisor",
  approved: "Aprobada",
  partially_approved: "Aprobada en parte",
  rejected: "Rechazada",
  expired: "Vencida",
};

export const NODE_LABEL: Record<string, string> = {
  input_guard: "Revisión de seguridad",
  router: "Clasificación",
  clarifier: "Aclaración",
  rag_agent: "Búsqueda en documentos",
  product_agent: "Consulta de productos",
  customer_agent: "Datos del cliente",
  composer: "Redacción",
  verifier: "Verificación de citas",
  escalation: "Escalamiento",
};

export const nodeLabel = (node: string) => NODE_LABEL[node] ?? node;
