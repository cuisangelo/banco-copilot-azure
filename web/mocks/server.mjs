// Local stand-in for copilot-api while it does not exist. Speaks the bank_contracts shapes exactly
// (verified by test_web_mock_contract.py). Usage: node mocks/server.mjs <port>
import { randomUUID } from "node:crypto";
import { createServer } from "node:http";

const port = Number(process.argv[2]);
if (!port) throw new Error("usage: node mocks/server.mjs <port>");

const PERSONAS = { ana: ["Ana", "Asesor"], bruno: ["Bruno", "Asesor"], sofia: ["Sofía", "Supervisor"] };
const GRANT_MINUTES = 30;
const STEP_MS = 280;

const tokens = new Map(); // token -> persona key
const accessRequests = new Map(); // id -> AccessRequest
const checkpoints = new Map(); // session_id -> access request id
const escalations = new Map(); // id -> decided?
const feedback = new Map(); // id -> Feedback, in insertion order

// Same patterns as copilot_api.guards.pii_mask.
const maskPii = (text) =>
  text
    .replace(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, "[EMAIL]")
    .replace(/\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b/g, "[RUT]")
    .replace(/\b\d(?:[ -]?\d){12,18}\b/g, "[PAN]");

const now = (offsetMinutes = 0) =>
  new Date(Date.now() + offsetMinutes * 60_000).toISOString().replace(/\.\d{3}Z$/, "Z");

function seedRequest(fields) {
  const request = {
    customer_id: "C-1013",
    fields: ["monthly_income", "current_debt"],
    purpose: "Evaluar si cumple renta y carga financiera para el crédito de consumo solicitado.",
    id: randomUUID(),
    requested_by: "bruno",
    status: "pending",
    created_at: now(-6),
    decided_by: null,
    decided_at: null,
    approved_fields: [],
    ...fields,
  };
  accessRequests.set(request.id, request);
}
seedRequest({});
seedRequest({
  customer_id: "C-1015",
  fields: ["payment_behavior"],
  purpose: "Confirmar comportamiento de pago antes de ofrecer aumento de cupo en tarjeta Oro.",
  status: "approved",
  created_at: now(-48),
  decided_by: "sofia",
  decided_at: now(-45),
  approved_fields: ["payment_behavior"],
});

const FIELD_LABELS = {
  monthly_income: "renta mensual",
  current_debt: "deuda vigente",
  payment_behavior: "comportamiento de pago",
  employment_tenure_months: "antigüedad laboral",
};
// Copied from data/customers.json (WP2) for the customers the demo scenarios use.
const CUSTOMERS = {
  "C-1007": {
    segment: "preferente",
    income_type: "dependiente",
    products: ["CTA-CORRIENTE", "TC-ORO"],
    level2: { monthly_income: "$2.350.000", current_debt: "$4.800.000", payment_behavior: "al día", employment_tenure_months: "18 meses" },
  },
  "C-1013": {
    segment: "personas",
    income_type: "dependiente",
    products: ["CTA-SUELDO", "TC-CLASICA", "CRED-CONSUMO"],
    level2: { monthly_income: "$720.000", current_debt: "$6.100.000", payment_behavior: "atraso de 90 días", employment_tenure_months: "19 meses" },
  },
};

const doc = (id, ref, snippet) => ({ id, kind: "doc", ref, snippet });
const product = (id, ref, snippet) => ({ id, kind: "product", ref, snippet });
const customer = (id, ref, snippet) => ({ id, kind: "customer", ref, snippet });
const claim = (text, ...citation_ids) => ({ text, citation_ids });

function trace(node, duration_ms, data, tokens_in = 0, tokens_out = 0) {
  const cost_usd = Number(((tokens_in * 0.4 + tokens_out * 1.6) / 1e6).toFixed(6));
  return { node, duration_ms, data, tokens_in, tokens_out, cost_usd };
}

function answer(status, message, extra = {}) {
  return {
    status,
    message,
    requirements: [],
    steps: [],
    citations: [],
    access_request: null,
    escalation: null,
    ...extra,
  };
}

function escalation(area, summary, evidence) {
  const draft = { id: randomUUID(), area, summary, evidence };
  escalations.set(draft.id, false);
  return draft;
}

const guard = (attack = false) => trace("input_guard", 64, { guardrail: "prompt_shields", attack_detected: attack });
const route = (name) => trace("router", 410, { route: name }, 612, 9);

function salaryAccount() {
  const citations = [
    doc("c1", "ficha-cuenta-sueldo §2. Requisitos", "Ser trabajador dependiente. Cédula de identidad vigente."),
    doc(
      "c2",
      "ficha-cuenta-sueldo §2. Requisitos",
      "Empleador con convenio de pago de remuneraciones vigente con Banco Austral. Última liquidación de sueldo o, si el trabajador recién ingresó a la empresa, contrato de trabajo firmado.",
    ),
    doc(
      "c3",
      "procedimiento-apertura-cuenta §2. Verificación de identidad",
      "Solicitar la cédula de identidad vigente y validarla en el verificador de documentos. Realizar la validación biométrica de huella o rostro.",
    ),
    doc(
      "c4",
      "procedimiento-apertura-cuenta §3. Pasos para Cuenta Sueldo",
      "Verificar en el buscador de convenios que el empleador tenga convenio vigente. Generar el contrato de cuenta vista y obtener la firma electrónica del cliente.",
    ),
  ];
  return {
    traces: [
      guard(),
      route("procedure"),
      trace("rag_agent", 820, {
        chunks: [
          { doc: "ficha-cuenta-sueldo", section: "2. Requisitos", score: 2.84 },
          { doc: "procedimiento-apertura-cuenta", section: "3. Pasos para Cuenta Sueldo", score: 2.41 },
          { doc: "procedimiento-apertura-cuenta", section: "2. Verificación de identidad", score: 2.12 },
        ],
      }, 96, 0),
      trace("composer", 1640, { claims: 7 }, 2310, 284),
      trace("verifier", 520, { groundedness: 0.97, uncited_claims: 0, contradictions: 0 }, 1180, 12),
    ],
    answer: answer("ok", "Para una cuenta sueldo de cliente dependiente pide estos documentos y sigue este orden. No se exige renta mínima.", {
      requirements: [
        claim("Cédula de identidad vigente", "c1"),
        claim("Empleador con convenio de pago de remuneraciones vigente con Banco Austral", "c2"),
        claim("Última liquidación de sueldo, o contrato de trabajo firmado si recién ingresó", "c2"),
      ],
      steps: [
        claim("Valida la cédula y haz la validación biométrica de huella o rostro", "c3"),
        claim("Verifica el convenio del empleador en el buscador de convenios", "c4"),
        claim("Genera el contrato de cuenta vista y obtén la firma electrónica", "c4"),
      ],
      citations,
    }),
  };
}

function compareCards() {
  return {
    traces: [
      guard(),
      route("product"),
      trace("product_agent", 690, { tool: "compare_products", args: { product_ids: ["TC-ORO", "TC-PLATINUM"] } }, 540, 38),
      trace("composer", 1210, { claims: 4 }, 1460, 196),
      trace("verifier", 480, { groundedness: 1.0, uncited_claims: 0, contradictions: 0 }, 902, 10),
    ],
    answer: answer("ok", "Comparación de las tarjetas Oro y Platinum con valores vigentes del sistema de productos.", {
      requirements: [
        claim("Oro: renta líquida mínima de $900.000 y edad desde 21 años", "p1"),
        claim("Platinum: renta líquida mínima de $1.800.000, 6 meses como cliente y pagos al día", "p2"),
      ],
      steps: [
        claim("Oro: mantención mensual de $4.990 y tasa anual de 32,4 %", "p1"),
        claim("Platinum: mantención mensual de $9.990 y tasa anual de 28,8 %", "p2"),
      ],
      citations: [
        product("p1", "producto:TC-ORO", "Tarjeta de Crédito Austral Oro. Mantención $4.990, tasa anual 32,4 %. Vigente desde 2026-03-01."),
        product("p2", "producto:TC-PLATINUM", "Tarjeta de Crédito Austral Platinum. Mantención $9.990, tasa anual 28,8 %. Vigente desde 2026-03-01."),
      ],
    }),
  };
}

function consumerLoan() {
  return {
    traces: [guard(), route("missing_context"), trace("clarifier", 540, { missing: ["income_type", "amount"] }, 488, 31)],
    answer: answer(
      "clarification",
      "Para orientarte necesito dos datos: ¿el cliente es dependiente o independiente, y qué monto quiere solicitar?",
    ),
  };
}

const MORTGAGE_TENURE = [
  doc("d1", "ficha-credito-hipotecario §3. Requisitos", "Dependientes: antigüedad laboral mínima de 12 meses con el empleador actual."),
  doc("d2", "circular-2026-07 §2. Cambio de criterio", "A contar del 1 de agosto de 2026, para dependientes la antigüedad laboral mínima con el empleador actual será de 24 meses."),
];

function mortgageTenure() {
  return {
    traces: [
      guard(),
      route("procedure"),
      trace("rag_agent", 760, {
        chunks: [
          { doc: "ficha-credito-hipotecario", section: "3. Requisitos", score: 2.77 },
          { doc: "circular-2026-07", section: "2. Cambio de criterio", score: 2.69 },
        ],
      }, 88, 0),
      trace("composer", 1350, { claims: 2 }, 1720, 141),
      trace("verifier", 610, { groundedness: 0.95, uncited_claims: 0, contradictions: 1, attribute: "antigüedad laboral mínima" }, 1004, 22),
      trace("escalation", 18, { draft: true, approval: "pending" }),
    ],
    answer: answer(
      "contradiction",
      "Las fuentes no coinciden en la antigüedad laboral mínima. No la confirmes al cliente hasta que el área de riesgo lo aclare.",
      {
        requirements: [
          claim("La ficha del hipotecario exige 12 meses de antigüedad laboral", "d1"),
          claim("La circular 2026-07 exige 24 meses desde el 1 de agosto de 2026", "d2"),
        ],
        citations: MORTGAGE_TENURE,
        escalation: escalation(
          "Riesgo de crédito hipotecario",
          "La ficha del crédito hipotecario (12 meses) y la circular 2026-07 (24 meses) difieren en la antigüedad laboral mínima de dependientes. Se solicita confirmar el requisito vigente y actualizar la ficha.",
          MORTGAGE_TENURE,
        ),
      },
    ),
  };
}

function outOfScope() {
  return {
    traces: [guard(), route("out_of_scope")],
    answer: answer("rejected", "Solo respondo sobre productos y procedimientos de Banco Austral. No doy opiniones de inversión."),
  };
}

function injection() {
  return {
    traces: [guard(true)],
    answer: answer("rejected", "La consulta intenta cambiar mis reglas de operación y no la proceso."),
  };
}

function notDocumented() {
  const evidence = [
    doc("e1", "ficha-cuenta-corriente §4. Condiciones comerciales", "Comisiones y condiciones de la Cuenta Corriente Austral, expresadas en pesos chilenos."),
  ];
  return {
    traces: [
      guard(),
      route("procedure"),
      trace("rag_agent", 700, { chunks: [{ doc: "ficha-cuenta-corriente", section: "4. Condiciones comerciales", score: 1.12 }], below_threshold: true }, 72, 0),
      trace("escalation", 15, { draft: true, approval: "pending" }),
    ],
    answer: answer("insufficient", "No lo encuentro en la documentación vigente. Si el cliente lo necesita, puedo escalar la consulta.", {
      escalation: escalation(
        "Productos y procedimientos",
        "Un cliente consulta por un producto o requisito que no figura en la documentación vigente. Se solicita confirmar si existe y bajo qué condiciones.",
        evidence,
      ),
    }),
  };
}

function unknownCustomer(customerId) {
  return {
    traces: [
      guard(),
      route("customer"),
      trace("customer_agent", 300, { tool: "get_customer_profile", args: { customer_id: customerId }, authz: "404" }, 380, 14),
    ],
    answer: answer("insufficient", `No encuentro al cliente ${customerId}. Revisa el identificador.`),
  };
}

function customerProfile(customerId) {
  const profile = CUSTOMERS[customerId];
  return {
    traces: [
      guard(),
      route("customer"),
      trace("customer_agent", 540, { tool: "get_customer_profile", args: { customer_id: customerId }, authz: "permitido" }, 410, 26),
      trace("composer", 990, { claims: 3 }, 1210, 132),
      trace("verifier", 450, { groundedness: 0.98, uncited_claims: 0, contradictions: 0 }, 860, 9),
    ],
    answer: answer("ok", `Perfil básico de ${customerId}. Para ofrecer crédito necesitarás datos de nivel 2.`, {
      requirements: [
        claim(`Segmento ${profile.segment}, con renta ${profile.income_type}`, "k1", "k2"),
        claim(`Productos vigentes: ${profile.products.join(", ")}`, "k3"),
      ],
      citations: [
        customer("k1", `cliente:${customerId} segment`, `Segmento: ${profile.segment}`),
        customer("k2", `cliente:${customerId} income_type`, `Tipo de renta: ${profile.income_type}`),
        customer("k3", `cliente:${customerId} products`, `Productos: ${profile.products.join(", ")}`),
      ],
    }),
  };
}

function requestAccess(sessionId, customerId, persona) {
  const fields = ["monthly_income", "employment_tenure_months"];
  const request = {
    customer_id: customerId,
    fields,
    purpose: `Verificar si ${customerId} cumple renta y antigüedad laboral para el crédito hipotecario.`,
    id: randomUUID(),
    requested_by: persona,
    status: "pending",
    created_at: now(),
    decided_by: null,
    decided_at: null,
    approved_fields: [],
  };
  accessRequests.set(request.id, request);
  checkpoints.set(sessionId, request.id);
  return {
    traces: [
      guard(),
      route("customer"),
      trace("customer_agent", 610, { tool: "get_customer_fields", args: { customer_id: customerId, fields }, authz: "403", denied_fields: fields }, 520, 64),
    ],
    answer: answer(
      "access_required",
      `Para saber si ${customerId} cumple necesito ver su renta mensual y antigüedad laboral. Envié la solicitud a un Supervisor.`,
      { access_request: request },
    ),
  };
}

const MORTGAGE_INCOME = doc("h1", "ficha-credito-hipotecario §3. Requisitos", "Renta líquida mensual mínima de $1.200.000, individual o complementada con cónyuge o conviviente civil.");

function resumed(request) {
  const values = CUSTOMERS[request.customer_id].level2;
  const approved = request.approved_fields;
  const denied = request.fields.filter((f) => !approved.includes(f));
  const label = (f) => `${FIELD_LABELS[f][0].toUpperCase()}${FIELD_LABELS[f].slice(1)}`;
  const citations = approved.map((f) => customer(`g-${f}`, `cliente:${request.customer_id} ${f}`, `${label(f)}: ${values[f]}`));
  citations.push(MORTGAGE_INCOME, ...MORTGAGE_TENURE);
  const support = { monthly_income: "h1", employment_tenure_months: "d1" };
  const requirements = [
    ...approved.map((f) => claim(`${label(f)}: ${values[f]}`, `g-${f}`, support[f])),
    ...denied.map((f) => claim(`${label(f)}: no autorizado — verificar con el cliente`, support[f])),
  ];
  const status = approved.length ? "ok" : "insufficient";
  const message = approved.length
    ? "Con los datos aprobados, esto es lo que se puede verificar. La decisión final es del área de riesgo."
    : "La solicitud fue rechazada. Respondo solo con los requisitos del producto; los datos del cliente quedan por verificar.";
  return {
    traces: [
      trace("customer_agent", 480, { tool: "get_customer_fields", args: { customer_id: request.customer_id, fields: approved }, authz: approved.length ? "permitido" : "403", fields: approved }, 380, 22),
      trace("composer", 1120, { claims: requirements.length }, 1340, 158),
      trace("verifier", 470, { groundedness: 0.96, uncited_claims: 0, contradictions: 0 }, 910, 11),
    ],
    answer: answer(status, message, { requirements, citations }),
  };
}

function chatScenario({ session_id, message, customer_id }, persona) {
  const text = message.toLowerCase();
  if (text.includes("tope")) return { error: { code: "token_cap", message: "Se alcanzó el tope diario de consumo. Vuelve a intentarlo mañana." } };
  if (text.includes("ignora")) return injection();
  if (text.includes("bitcoin") || text.includes("invert")) return outOfScope();
  if (customer_id) {
    if (!persona || PERSONAS[persona][1] !== "Asesor") {
      return { error: { code: "unauthorized", message: "Para consultar datos de un cliente elige una persona con rol Asesor." } };
    }
    if (!CUSTOMERS[customer_id]) return unknownCustomer(customer_id);
    if (/cumple|renta|deuda|hipotecario/.test(text)) return requestAccess(session_id, customer_id, persona);
    return customerProfile(customer_id);
  }
  if (text.includes("sueldo")) return salaryAccount();
  if (text.includes("oro") || text.includes("platinum")) return compareCards();
  if (text.includes("crédito") || text.includes("credito")) {
    return text.includes("hipotecario") ? mortgageTenure() : consumerLoan();
  }
  if (text.includes("hipotecario")) return mortgageTenure();
  return notDocumented();
}

function cors(res) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, Authorization");
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
}

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

async function sse(res, { traces = [], answer: final, error }) {
  res.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
  for (const event of traces) {
    await new Promise((r) => setTimeout(r, STEP_MS));
    res.write(`event: trace\ndata: ${JSON.stringify(event)}\n\n`);
  }
  await new Promise((r) => setTimeout(r, STEP_MS));
  res.end(error ? `event: error\ndata: ${JSON.stringify(error)}\n\n` : `event: answer\ndata: ${JSON.stringify(final)}\n\n`);
}

async function readBody(req) {
  let raw = "";
  for await (const chunk of req) raw += chunk;
  return raw ? JSON.parse(raw) : null;
}

createServer(async (req, res) => {
  cors(res);
  if (req.method === "OPTIONS") return res.writeHead(204).end();

  const url = new URL(req.url, "http://mock");
  const header = req.headers.authorization;
  let persona = null;
  if (header) {
    persona = tokens.get(header.replace(/^Bearer /, ""));
    if (!persona) return json(res, 401, { detail: "token inválido o vencido" });
  }
  const role = persona && PERSONAS[persona][1];
  const body = await readBody(req);
  let m;

  if (req.method === "POST" && url.pathname === "/demo/session") {
    if (!PERSONAS[body?.persona]) return json(res, 422, { detail: "persona desconocida" });
    const token = `mock-${body.persona}-${randomUUID()}`;
    tokens.set(token, body.persona);
    const [name, personaRole] = PERSONAS[body.persona];
    return json(res, 200, { token, name, role: personaRole });
  }

  if (req.method === "POST" && url.pathname === "/chat") return sse(res, chatScenario(body, persona));

  if (req.method === "POST" && (m = url.pathname.match(/^\/sessions\/([^/]+)\/resume$/))) {
    const request = accessRequests.get(checkpoints.get(m[1]));
    if (!request || request.status === "pending") return json(res, 409, { detail: "nada que reanudar" });
    checkpoints.delete(m[1]);
    return sse(res, resumed(request));
  }

  if (req.method === "POST" && (m = url.pathname.match(/^\/escalations\/([^/]+)\/decision$/))) {
    if (!escalations.has(m[1])) return json(res, 404, { detail: "escalamiento inexistente" });
    if (escalations.get(m[1])) return json(res, 409, { detail: "ya decidido" });
    escalations.set(m[1], true);
    return json(res, 200, body.approve ? { ticket_id: `ESC-${Math.floor(1000 + Math.random() * 9000)}` } : { discarded: true });
  }

  if (req.method === "GET" && url.pathname === "/access-requests") {
    if (role !== "Supervisor") return json(res, 403, { detail: "solo Supervisor" });
    const status = url.searchParams.get("status");
    return json(res, 200, [...accessRequests.values()].filter((r) => !status || r.status === status).reverse());
  }

  if (req.method === "GET" && (m = url.pathname.match(/^\/access-requests\/([^/]+)$/))) {
    const request = accessRequests.get(m[1]);
    if (!request) return json(res, 404, { detail: "solicitud inexistente" });
    if (role !== "Supervisor" && persona !== request.requested_by) return json(res, 403, { detail: "sin acceso" });
    return json(res, 200, request);
  }

  if (req.method === "POST" && (m = url.pathname.match(/^\/access-requests\/([^/]+)\/decision$/))) {
    const request = accessRequests.get(m[1]);
    if (!request) return json(res, 404, { detail: "solicitud inexistente" });
    if (role !== "Supervisor" || persona === request.requested_by) return json(res, 403, { detail: "no puedes decidir esta solicitud" });
    if (request.status !== "pending") return json(res, 409, { detail: "ya decidida" });
    const approved = body.approved_fields.filter((f) => request.fields.includes(f));
    Object.assign(request, {
      status: approved.length === 0 ? "rejected" : approved.length === request.fields.length ? "approved" : "partially_approved",
      decided_by: persona,
      decided_at: now(),
      approved_fields: approved,
    });
    if (approved.length) setTimeout(() => request.status !== "pending" && (request.status = "expired"), GRANT_MINUTES * 60_000).unref();
    return json(res, 200, request);
  }

  if (req.method === "POST" && url.pathname === "/feedback") {
    const actor = persona ?? "anonymous";
    const id = `feedback:${actor}:${body.session_id}:${body.turn_index}`;
    if (feedback.has(id)) return json(res, 409, { detail: "Ya calificaste esta respuesta." });
    const { session_id, turn_index, rating, comment = null, answer_status } = body;
    feedback.set(id, {
      session_id,
      turn_index,
      rating,
      comment: comment && maskPii(comment),
      answer_status,
      id,
      actor,
      created_at: now(),
    });
    return json(res, 201, { id });
  }

  if (req.method === "GET" && url.pathname === "/feedback") {
    if (role !== "Supervisor") return json(res, 403, { detail: "solo Supervisor" });
    return json(res, 200, [...feedback.values()].reverse().slice(0, Number(url.searchParams.get("limit") ?? 50)));
  }

  json(res, 404, { detail: "ruta inexistente en el mock" });
}).listen(port, () => console.log(`copilot-api mock on http://localhost:${port}`));
