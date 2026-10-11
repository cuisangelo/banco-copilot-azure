// Drawn on the navy panel: every color below is checked for AA against #002a6e and the box fills.
const LINE = "#7fd3f2";
const SUB = "#c9d6ee";

type BoxProps = {
  x: number;
  y: number;
  w: number;
  h: number;
  title: string;
  sub?: string[];
  region?: string;
  tone?: "plain" | "core" | "echo";
};

function Box({ x, y, w, h, title, sub = [], region, tone = "plain" }: BoxProps) {
  const fill = tone === "core" ? "#0047bb" : "rgb(255 255 255 / 0.07)";
  const stroke = tone === "core" ? "#00a3e0" : "rgb(255 255 255 / 0.32)";
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={h}
        rx={12}
        fill={fill}
        stroke={stroke}
        strokeWidth={tone === "core" ? 2 : 1.2}
        strokeDasharray={tone === "echo" ? "6 5" : undefined}
      />
      <text x={x + 16} y={y + 26} className="font-display" fontSize={15} fontWeight={700} fill="white">
        {title}
      </text>
      {sub.map((line, i) => (
        <text key={i} x={x + 16} y={y + 46 + i * 17} fontSize={13} fill={tone === "core" ? "white" : SUB}>
          {line}
        </text>
      ))}
      {region && (
        <text x={x + w - 12} y={y + 26} textAnchor="end" fontSize={12} fontWeight={600} fill={LINE}>
          {region}
        </text>
      )}
    </g>
  );
}

function Arrow({ d }: { d: string }) {
  return <path d={d} fill="none" stroke={LINE} strokeWidth={1.6} markerEnd="url(#arch-arrow)" />;
}

function Band({ y, h, title, sub }: { y: number; h: number; title: string; sub: string }) {
  return (
    <g>
      <rect x={20} y={y} width={1080} height={h} rx={14} fill="rgb(255 255 255 / 0.03)" stroke="rgb(255 255 255 / 0.18)" />
      <text x={40} y={y + 34} className="font-display" fontSize={15} fontWeight={800} fill="white">
        {title}
      </text>
      <text x={40} y={y + 54} fontSize={13} fill={SUB}>
        {sub}
      </text>
    </g>
  );
}

const DEPS_X = 680;
const DEPS_W = 230;
const DEPS_H = 70;
const DEPS: { y: number; title: string; sub: string[]; region?: string }[] = [
  { y: 30, title: "Content Safety", sub: ["Prompt Shields y groundedness"], region: "East US 2" },
  { y: 114, title: "Foundry / Azure OpenAI", sub: ["gpt-4.1-mini", "text-embedding-3-small"] },
  { y: 198, title: "AI Search", sub: ["híbrida + semántica"] },
  { y: 282, title: "Cosmos DB", sub: ["sesiones, checkpoints, solicitudes,", "permisos y auditoría"], region: "East US 2" },
  { y: 366, title: "mcp-bank", sub: ["MCP, ingress interno"] },
];
const BUS_X = 645;
const CORE_Y = 240;

const PILLS: { x: number; w: number; label: string }[] = [
  { x: 200, w: 150, label: "Managed Identity" },
  { x: 366, w: 100, label: "Key Vault" },
  { x: 482, w: 250, label: "App Insights + OpenTelemetry" },
  { x: 748, w: 64, label: "ACR" },
  { x: 828, w: 106, label: "Terraform" },
];

export function ArchitectureDiagram() {
  return (
    <svg
      viewBox="0 0 1120 830"
      role="img"
      aria-labelledby="arch-title arch-desc"
      className="block h-auto w-full min-w-[960px] font-sans"
    >
      <title id="arch-title">Diagrama de arquitectura del copiloto en Azure</title>
      <desc id="arch-desc">
        El asesor o supervisor usa Static Web Apps, que llama por HTTPS y SSE con el JWT de la persona a copilot-api en
        Container Apps. copilot-api ejecuta el workflow de Agent Framework y consulta Content Safety, Foundry con Azure
        OpenAI, AI Search, Cosmos DB y mcp-bank. mcp-bank pasa por API Management Consumption hacia products-api y
        customers-api. La ingesta va de Blob Storage a Event Grid, a una Function Flex y a AI Search. Transversales:
        Managed Identity, Key Vault, App Insights con OpenTelemetry, ACR y Terraform.
      </desc>
      <defs>
        <marker id="arch-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 10 5 0 10z" fill={LINE} />
        </marker>
      </defs>

      <Box x={20} y={200} w={150} h={80} title="Asesor" sub={["o Supervisor,", "con persona demo"]} />
      <Arrow d="M170 240H198" />
      <Box x={200} y={200} w={150} h={80} title="Static Web Apps" sub={["Next.js estático"]} />
      <text x={216} y={263} fontSize={12} fontWeight={600} fill={LINE}>
        East US 2
      </text>
      <text x={380} y={222} textAnchor="middle" fontSize={11.5} fill={SUB}>
        SSE
      </text>
      <text x={380} y={262} textAnchor="middle" fontSize={11.5} fill={SUB}>
        + JWT
      </text>
      <Arrow d="M350 240H408" />

      <Box
        x={410}
        y={120}
        w={200}
        h={240}
        tone="core"
        title="copilot-api"
        sub={["Container Apps, externo", "", "Workflow de", "Agent Framework", "", "Tope diario de tokens", "Rate limit por IP"]}
      />

      <path d={`M610 ${CORE_Y}H${BUS_X}`} stroke={LINE} strokeWidth={1.6} />
      <path d={`M${BUS_X} ${DEPS[0].y + DEPS_H / 2}V${DEPS[4].y + DEPS_H / 2}`} stroke={LINE} strokeWidth={1.6} />
      {DEPS.map((dep) => (
        <g key={dep.title}>
          <Arrow d={`M${BUS_X} ${dep.y + DEPS_H / 2}H${DEPS_X - 2}`} />
          <Box x={DEPS_X} y={dep.y} w={DEPS_W} h={DEPS_H} title={dep.title} sub={dep.sub} region={dep.region} />
        </g>
      ))}

      <Arrow d="M795 436V468" />
      <text x={807} y={457} fontSize={11.5} fill={SUB}>
        JWT reenviado
      </text>
      <Box x={DEPS_X} y={470} w={DEPS_W} h={70} title="API Management" sub={["Consumption, inyecta", "X-Backend-Secret"]} />
      <path d="M910 505H930M930 464V544" stroke={LINE} strokeWidth={1.6} fill="none" />
      <Arrow d="M930 464H948" />
      <Arrow d="M930 544H948" />
      <Box x={950} y={436} w={150} h={56} title="products-api" sub={["Container App"]} />
      <Box x={950} y={516} w={150} h={56} title="customers-api" sub={["niveles y permisos"]} />

      <Band y={606} h={110} title="Ingesta" sub="al subir un documento" />
      <Box x={200} y={634} w={170} h={56} title="Blob Storage" sub={["contenedor docs"]} />
      <Arrow d="M370 662H418" />
      <Box x={420} y={634} w={170} h={56} title="Event Grid" sub={["system topic"]} />
      <Arrow d="M590 662H638" />
      <Box x={640} y={634} w={200} h={56} title="Function Flex" sub={["chunks + embeddings"]} />
      <Arrow d="M840 662H888" />
      <Box x={890} y={634} w={190} h={56} title="AI Search" sub={["índice bank-docs"]} tone="echo" />

      <Band y={732} h={84} title="Transversal" sub="en todos los servicios" />
      {PILLS.map((pill) => (
        <g key={pill.label}>
          <rect x={pill.x} y={756} width={pill.w} height={36} rx={18} fill="rgb(255 255 255 / 0.07)" stroke="rgb(255 255 255 / 0.32)" />
          <text x={pill.x + pill.w / 2} y={779} textAnchor="middle" fontSize={13.5} fontWeight={600} fill="white">
            {pill.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
