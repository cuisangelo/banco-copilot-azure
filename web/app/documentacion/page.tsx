// Server component on purpose: its content ships only in documentacion.html/.txt, which Static Web Apps
// serves behind built-in auth. Client components imported here end up in public chunks.
import type { Metadata } from "next";
import Link from "next/link";
import { ApiStatus } from "@/components/ApiStatus";
import { LockIcon } from "@/components/icons";
import { FIELD_LABEL, NODE_LABEL } from "@/lib/labels";
import { GRANT_MINUTES, LEVEL2_FIELDS } from "@/lib/types";
import { ArchitectureDiagram } from "./ArchitectureDiagram";
import { portalUrl } from "./azure";
import { loadDeployment } from "./inventory";

export const metadata: Metadata = {
  title: "Documentación · Banco Austral",
  description: "Arquitectura, workflow y recursos desplegados del copiloto de atención.",
};

// Guaranteed at build time by next.config.ts.
const JWKS_URL = `${process.env.NEXT_PUBLIC_API_BASE_URL}/.well-known/jwks.json`;

const SECTIONS = [
  { id: "arquitectura", label: "Arquitectura" },
  { id: "workflow", label: "Workflow" },
  { id: "busqueda", label: "Búsqueda" },
  { id: "niveles", label: "Niveles de acceso" },
  { id: "recursos", label: "Recursos en Azure" },
  { id: "evidencia", label: "Evidencia pública" },
  { id: "decisiones", label: "Decisiones" },
  { id: "produccion", label: "Producción objetivo" },
];

const WORKFLOW: { node: string; text: string; hitl?: boolean }[] = [
  { node: "input_guard", text: "Prompt Shields revisa el texto del asesor. Si detecta un ataque, la consulta se rechaza." },
  {
    node: "router",
    text: "Clasifica la consulta: procedimiento, producto, cliente, mixta o fuera de alcance. Si falta un dato, el clarificador lo pide antes de seguir.",
  },
  {
    node: "rag_agent",
    text: "Busca en AI Search en modo híbrido o agéntico, según elija el asesor. Los fragmentos pasan por Prompt Shields antes de entrar al prompt.",
  },
  { node: "product_agent", text: "Trae tasas, comisiones y comparaciones vigentes con las tools de mcp-bank." },
  {
    node: "customer_agent",
    text: "Lee el perfil del cliente (nivel 1) y, si la pregunta lo exige, campos de nivel 2. Un 403 de customers-api abre una solicitud de acceso.",
  },
  {
    node: "composer",
    text: "Arma requisitos, pasos y citas. Cada afirmación referencia un documento, un producto o un campo del cliente.",
  },
  {
    node: "verifier",
    text: "Comprueba groundedness, que cada afirmación tenga cita y que dos fuentes no den valores distintos para lo mismo.",
  },
  {
    node: "relevance",
    text: "Revisa que la respuesta conteste lo que se preguntó. Si trata otra cosa, responde que no puede ayudar con eso; si cubre una parte, dice qué faltó.",
  },
  {
    node: "escalation",
    text: "Si falta información o hay contradicción, propone un ticket redactado. Solo se crea si el asesor lo aprueba.",
    hitl: true,
  },
];

const RETRIEVAL_MODES: { mode: string; name: string; points: string[] }[] = [
  {
    mode: "hybrid",
    name: "RAG híbrido",
    points: [
      "Una sola búsqueda con la consulta que reescribe el router.",
      "Combina palabras clave (BM25) y similitud de vectores (text-embedding-3-small); el reranking semántico ordena el resultado y quedan los 8 mejores fragmentos.",
      "No llama al modelo de chat: solo cuesta un embedding.",
      "Corre en AI Search Free y está siempre activo.",
      "Una pregunta con varios temas sigue siendo una búsqueda: en una comparación, los fragmentos de un producto pueden desplazar a los del otro.",
    ],
  },
  {
    mode: "agentic",
    name: "Agéntica",
    points: [
      "La knowledge base de AI Search usa gpt-4.1-mini para dividir la pregunta en subconsultas: una comparación se vuelve una búsqueda por producto.",
      "Cada subconsulta corre con reranking semántico; se juntan las referencias y quedan las 8 de mayor puntaje.",
      "La planificación gasta tokens del modelo de chat, que cuentan para el tope diario y el costo del inspector. El inspector muestra las subconsultas.",
      "Necesita AI Search Basic (unos USD 0,10 por hora): en Free el planificador no puede llamar al modelo con identidad administrada, y no usamos llaves. Por eso vive en un servicio aparte, con una copia del índice, encendido solo para demos.",
      "Usa la API preview 2026-08-01: la versión GA solo acepta subconsultas escritas por quien llama. Si una subconsulta falla, el turno da error en vez de responder con resultados parciales.",
    ],
  },
];

const LEVELS: { level: number; name: string; fields: string; how: string }[] = [
  { level: 0, name: "Sin cliente", fields: "Solo documentos y productos", how: "Siempre, incluso sin persona" },
  {
    level: 1,
    name: "Perfil básico",
    fields: "Segmento, tipo de renta, productos contratados, antigüedad como cliente",
    how: "Rol Asesor, al indicar el id del cliente",
  },
  {
    level: 2,
    name: "Sensible",
    fields: LEVEL2_FIELDS.map((f) => FIELD_LABEL[f]).join(", "),
    how: `Permiso aprobado por un Supervisor: por cliente, por campo, con propósito y por ${GRANT_MINUTES} minutos`,
  },
  {
    level: 3,
    name: "Nunca",
    fields: "RUT completo, dirección, movimientos, datos de terceros",
    how: "No existe endpoint que los devuelva",
  },
];

const DECISIONS: { title: string; text: string }[] = [
  {
    title: "Free Trial: USD 20–30 estimados",
    text: "El crédito es de USD 200 por 30 días. Casi todo usa cuotas gratis o escala a cero: Container Apps, AI Search Free, Cosmos DB free tier, Static Web Apps Free, APIM Consumption y Functions Flex.",
  },
  {
    title: "Dos regiones",
    text: "El resto vive en Canada East. Cosmos DB y Content Safety están en East US 2: Canada East rechazó Cosmos DB para esta suscripción y no ofrece groundedness.",
  },
  {
    title: "APIM Consumption, sin MCP nativo",
    text: "El MCP nativo de API Management no existe en Consumption. mcp-bank es un servidor MCP propio en Container Apps y APIM queda como gateway de las APIs, a USD 0.",
  },
  {
    title: "Personas con forma de Entra ID",
    text: "Los visitantes no tienen cuenta en el tenant. copilot-api firma un JWT RS256 con sub y roles (Asesor o Supervisor), igual que los app roles de Entra: pasar a Entra real cambia el emisor y la JWKS, no la autorización.",
  },
];

const PRODUCTION = [
  "AKS o Container Apps dedicado",
  "VNet con Private Endpoints y DNS privado",
  "APIM Standard v2 con MCP nativo y validate-jwt",
  "Azure Managed Redis",
  "Login real con Entra ID y app roles (Asesor, Supervisor), con Conditional Access",
  "Permisos con PIM o un flujo de aprobación corporativo",
  "Content Safety con filtros personalizados",
  "Evaluación continua en Foundry",
];

function Section({ id, title, lead, children }: { id: string; title: string; lead?: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-title`} className="scroll-mt-6 pt-14">
      <h2 id={`${id}-title`} className="font-display text-2xl font-bold tracking-tight text-navy sm:text-[1.75rem]">
        {title}
      </h2>
      {lead && <p className="mt-2 max-w-3xl text-[1.05rem] leading-relaxed text-muted">{lead}</p>}
      <div className="mt-6">{children}</div>
    </section>
  );
}

const FLOW = [
  "El asesor o supervisor abre la app, servida por Static Web Apps.",
  "El navegador envía la consulta a copilot-api por HTTPS/SSE, con el JWT de la persona demo.",
  "Content Safety revisa la consulta y los documentos con Prompt Shields, y la respuesta con groundedness.",
  "copilot-api busca en AI Search y redacta con Azure OpenAI.",
  "Sesiones, checkpoints, solicitudes de acceso, permisos y auditoría quedan en Cosmos DB.",
  "Las tools de productos y clientes van por MCP a mcp-bank, que no es accesible desde internet.",
  "mcp-bank llama a API Management con la subscription key; APIM agrega X-Backend-Secret y customers-api valida el JWT y los permisos.",
];

const INGESTION = [
  "Un documento nuevo en el contenedor docs emite un evento BlobCreated.",
  "Event Grid dispara la Function de ingesta.",
  "La Function divide por sección, genera embeddings e indexa en AI Search.",
];

function Legend({ label, steps, hollow = false }: { label: string; steps: string[]; hollow?: boolean }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-navy">{label}</h3>
      <ol aria-label={label} className="mt-2 space-y-1.5">
        {steps.map((step, i) => (
          <li key={step} className="flex gap-2.5 text-sm leading-snug text-ink">
            <span
              className={`flex size-5 shrink-0 items-center justify-center rounded-full text-[0.7rem] font-bold ring-[1.5px] ring-navy ${
                hollow ? "bg-white text-navy" : "bg-navy text-white"
              }`}
              aria-hidden
            >
              {hollow ? String.fromCharCode(65 + i) : i + 1}
            </span>
            {step}
          </li>
        ))}
      </ol>
    </div>
  );
}

const Code = ({ children }: { children: React.ReactNode }) => (
  <code className="rounded-md bg-sky px-1.5 py-0.5 font-mono text-[0.85em] text-navy">{children}</code>
);

export default function DocumentationPage() {
  const deployment = loadDeployment();
  return (
    <main className="relative min-h-0 flex-1 overflow-y-auto">
      <div className="mx-auto max-w-[1200px] px-4 pb-20 sm:px-6">
        <header className="pt-10 sm:pt-14">
          <h1 className="max-w-3xl font-display text-3xl leading-[1.15] font-extrabold tracking-tight text-navy sm:text-[2.6rem]">
            Cómo está hecho el copiloto de atención
          </h1>
          <p className="mt-4 max-w-2xl text-lg leading-relaxed text-ink">
            Un copiloto para asesores de un banco ficticio: responde con requisitos, pasos y la fuente de cada dato, y
            solo usa datos del cliente que un Supervisor autorizó. Corre en Azure con servicios que escalan a cero.
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-3">
            <Link
              href="/"
              className="rounded-full bg-brand px-5 py-2.5 font-semibold text-white shadow-soft transition-colors hover:bg-brand-hover"
            >
              Probar el copiloto
            </Link>
            <a
              href="/.auth/logout?post_logout_redirect_uri=/"
              className="rounded-full px-5 py-2.5 font-semibold text-brand ring-1 ring-line transition-colors hover:bg-sky"
            >
              Cerrar sesión
            </a>
          </div>
          <p className="mt-3 text-sm text-muted">Datos sintéticos; ninguna operación bancaria es real.</p>
          <nav aria-label="En esta página" className="mt-8 border-t border-line pt-4">
            <ul className="flex flex-wrap gap-2">
              {SECTIONS.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className="block rounded-full bg-white px-3 py-1.5 text-sm font-semibold text-navy ring-1 ring-line transition-colors hover:bg-sky"
                  >
                    {s.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </header>

        <Section
          id="arquitectura"
          title="Arquitectura"
          lead="Cada ícono es un recurso desplegado: ábrelo para verlo en el portal de Azure. copilot-api es la única frontera pública; los datos de clientes solo llegan por mcp-bank y API Management, con la identidad de la persona en el JWT."
        >
          <figure className="overflow-hidden rounded-3xl bg-white shadow-soft ring-1 ring-line">
            <p className="border-b border-line px-5 py-2.5 text-sm text-muted xl:hidden">
              Desliza para ver el diagrama completo.
            </p>
            <div className="overflow-x-auto p-3 sm:p-4" tabIndex={0} aria-label="Diagrama de arquitectura, desplazable">
              <ArchitectureDiagram deployment={deployment} />
            </div>
            <figcaption className="grid gap-6 border-t border-line px-5 py-5 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <Legend label="Flujo principal" steps={FLOW} />
              <Legend label="Ingesta" steps={INGESTION} hollow />
              <p className="text-xs text-muted md:col-span-2">Íconos: Microsoft Azure Architecture Icons</p>
            </figcaption>
          </figure>
        </Section>

        <Section
          id="workflow"
          title="Workflow del copiloto"
          lead="Un grafo de Agent Framework con un executor por nodo. Cada nodo emite un evento al inspector con su duración, tokens y costo estimado."
        >
          <ol aria-label="Nodos del workflow" className="max-w-3xl">
            {WORKFLOW.map((step, i) => (
              <li key={step.node} data-node={step.node} className="relative flex gap-4 pb-6 last:pb-0">
                {i < WORKFLOW.length - 1 && (
                  <span className="absolute top-9 bottom-0 left-[17px] w-0.5 bg-line" aria-hidden />
                )}
                <span className="relative flex size-9 shrink-0 items-center justify-center rounded-full bg-brand font-display text-sm font-bold text-white">
                  {i + 1}
                </span>
                <div className="min-w-0 pt-1">
                  <h3 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display font-bold text-navy">
                    {NODE_LABEL[step.node]}
                    <Code>{step.node}</Code>
                    {step.hitl && (
                      <span className="rounded-full bg-contradiction/10 px-2 py-0.5 font-sans text-xs font-semibold text-contradiction-ink">
                        Aprobación humana
                      </span>
                    )}
                  </h3>
                  <p className="mt-1 leading-relaxed text-ink">{step.text}</p>
                  {step.node === "customer_agent" && (
                    <div className="mt-3 rounded-2xl border-l-4 border-access bg-access/5 p-4">
                      <p className="flex flex-wrap items-center gap-2 text-sm font-semibold text-access">
                        <Code>access_required</Code>
                        <span aria-hidden>→</span>
                        <span>bandeja del Supervisor</span>
                        <span aria-hidden>→</span>
                        <Code>resume</Code>
                      </p>
                      <p className="mt-2 text-sm leading-relaxed text-ink">
                        El workflow queda en checkpoint en Cosmos DB. El Supervisor aprueba campo por campo o rechaza;
                        al reanudar, la tool devuelve solo lo aprobado y lo demás aparece como no autorizado.
                      </p>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </Section>

        <Section
          id="busqueda"
          title="Búsqueda: híbrida o agéntica"
          lead="El asesor elige el modo en cada pregunta. La diferencia está en quién arma las consultas: en la híbrida es una sola, la del router; en la agéntica un modelo la divide en varias."
        >
          <div className="grid gap-4 md:grid-cols-2">
            {RETRIEVAL_MODES.map((m) => (
              <div key={m.mode} className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-line">
                <h3 className="flex flex-wrap items-center gap-x-2 gap-y-1 font-display font-bold text-navy">
                  {m.name}
                  <Code>{m.mode}</Code>
                </h3>
                <ul className="mt-3 list-disc space-y-2 pl-5 leading-relaxed text-ink marker:text-brand">
                  {m.points.map((point) => (
                    <li key={point}>{point}</li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
          <p className="mt-6 max-w-3xl leading-relaxed text-ink">
            Lo que sigue es igual en los dos modos: el filtro de relevancia, Prompt Shields sobre los fragmentos, el
            composer y el verificador. Una consulta reanudada tras una aprobación no vuelve a buscar, porque recupera
            los fragmentos del checkpoint. La opción agéntica solo aparece en el chat cuando <Code>GET /status</Code>{" "}
            la informa activa; si no, <Code>/chat</Code> responde 409.
          </p>
        </Section>

        <Section
          id="niveles"
          title="Niveles de acceso a datos del cliente"
          lead="Todos los clientes son sintéticos. Cuanto más sensible el dato, más difícil obtenerlo, y el nivel 3 no se obtiene nunca."
        >
          <div className="overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-line">
            <div
              className="hidden grid-cols-[minmax(0,13rem)_minmax(0,1fr)_minmax(0,1fr)] gap-6 border-b border-line bg-canvas px-5 py-3 text-sm font-semibold text-muted md:grid"
              aria-hidden
            >
              <span>Nivel</span>
              <span>Campos</span>
              <span>Cómo se obtiene</span>
            </div>
            <ul aria-label="Niveles de acceso" className="divide-y divide-line">
              {LEVELS.map((l) => (
                <li
                  key={l.level}
                  className="grid gap-2 px-5 py-4 md:grid-cols-[minmax(0,13rem)_minmax(0,1fr)_minmax(0,1fr)] md:gap-6"
                >
                  <h3 className="flex items-center gap-3 font-display font-bold text-navy">
                    <span
                      className={`flex size-8 shrink-0 items-center justify-center rounded-full text-sm text-white ${
                        l.level === 2 ? "bg-access" : l.level === 3 ? "bg-reject" : "bg-brand"
                      }`}
                    >
                      {l.level}
                    </span>
                    {l.name}
                  </h3>
                  <p className="text-ink">
                    <span className="font-semibold text-muted md:hidden">Campos: </span>
                    {l.fields}
                  </p>
                  <p className="text-ink">
                    <span className="font-semibold text-muted md:hidden">Cómo se obtiene: </span>
                    {l.how}
                  </p>
                </li>
              ))}
            </ul>
          </div>

          <div className="mt-8 max-w-3xl">
            <h3 className="font-display text-lg font-bold text-navy">Por qué la autorización vive en customers-api</h3>
            <p className="mt-2 leading-relaxed text-ink">
              Un prompt se puede manipular; un endpoint que nunca devuelve el dato, no. El modelo no puede ampliar lo que
              nunca recibe.
            </p>
            <ul className="mt-3 list-disc space-y-2 pl-5 leading-relaxed text-ink marker:text-brand">
              <li>
                El modelo solo elige <Code>customer_id</Code> y <Code>fields</Code>. La identidad viaja en el JWT, que
                copilot-api pone en el transporte MCP: el modelo no lo ve ni puede alterarlo.
              </li>
              <li>
                customers-api valida firma, emisor, expiración y rol. Para nivel 2 exige un permiso vigente que coincida
                con el asesor, el cliente y cada campo pedido; si falta uno, responde 403.
              </li>
              <li>Un Supervisor no puede aprobar su propia solicitud, y el rol Asesor no puede aprobar ninguna.</li>
              <li>Los campos de nivel 3 no existen en ningún modelo de respuesta.</li>
            </ul>
          </div>
        </Section>

        <Section
          id="recursos"
          title="Recursos desplegados"
          lead={`Todo vive en el grupo de recursos ${deployment.resourceGroup} y se crea con Terraform.`}
        >
          <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
            <a
              href={`${deployment.resourceGroupUrl}/overview`}
              target="_blank"
              rel="noopener noreferrer"
              className="rounded-full bg-navy px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-brand"
            >
              Grupo de recursos {deployment.resourceGroup}
            </a>
            <p className="flex items-center gap-1.5 text-sm text-muted">
              <LockIcon className="size-4 shrink-0" />
              Los enlaces al portal requieren acceso a la suscripción del autor.
            </p>
          </div>
          <ul
            aria-label="Recursos desplegados"
            className="divide-y divide-line overflow-hidden rounded-2xl bg-white shadow-soft ring-1 ring-line"
          >
            {deployment.resources.map((r) => (
              <li
                key={r.name}
                className="grid gap-x-6 gap-y-2 px-5 py-4 lg:grid-cols-[minmax(0,17rem)_minmax(0,1fr)_auto] lg:items-center"
              >
                <div className="min-w-0">
                  <h3 className="font-mono text-[0.95rem] font-semibold break-all text-navy">{r.name}</h3>
                  <p className="mt-0.5 text-sm text-muted">
                    {r.service}, {r.regionLabel}
                  </p>
                </div>
                <p className="text-[0.95rem] leading-relaxed text-ink">{r.role}</p>
                <a
                  href={portalUrl(deployment, r)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="justify-self-start rounded-full px-4 py-2 text-sm font-semibold whitespace-nowrap text-brand ring-1 ring-brand/30 transition-colors hover:bg-sky"
                >
                  Ver en Azure<span className="sr-only">: {r.name}</span>
                </a>
              </li>
            ))}
          </ul>
        </Section>

        <Section
          id="evidencia"
          title="Evidencia pública"
          lead="Esto lo puede comprobar cualquiera, sin acceso a la suscripción."
        >
          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-line">
              <h3 className="text-sm font-semibold text-muted">Estado en vivo de copilot-api</h3>
              <div className="mt-2">
                <ApiStatus />
              </div>
              <p className="mt-2 text-sm leading-relaxed text-muted">
                Medido desde tu navegador al abrir esta página. Sin tráfico, Container Apps escala a cero y el primer
                pedido tarda más.
              </p>
            </div>
            <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-line">
              <h3 className="text-sm font-semibold text-muted">Firma de los tokens</h3>
              <p className="mt-2 leading-relaxed text-ink">
                copilot-api publica la{" "}
                <a
                  href={JWKS_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-semibold text-brand underline underline-offset-2 hover:text-brand-hover"
                >
                  llave pública de las personas demo
                </a>
                . customers-api verifica con ella cada JWT; solo copilot-api firma, con la llave privada en Key Vault.
              </p>
            </div>
          </div>
        </Section>

        <Section id="decisiones" title="Decisiones y tradeoffs">
          <dl className="grid gap-x-10 gap-y-6 md:grid-cols-2">
            {DECISIONS.map((d) => (
              <div key={d.title} className="border-t-2 border-brand pt-3">
                <dt className="font-display font-bold text-navy">{d.title}</dt>
                <dd className="mt-1.5 leading-relaxed text-ink">{d.text}</dd>
              </div>
            ))}
          </dl>
        </Section>

        <Section
          id="produccion"
          title="Producción objetivo"
          lead="Lo que cambiaría en un banco real. Queda documentado y no se desplegó: no cabe en un Free Trial o queda fuera del alcance de la demo."
        >
          <ul className="grid gap-3 sm:grid-cols-2">
            {PRODUCTION.map((item) => (
              <li key={item} className="rounded-xl bg-sky px-4 py-3 font-semibold text-navy">
                {item}
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </main>
  );
}
