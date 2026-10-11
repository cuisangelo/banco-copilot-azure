import { RESOURCE_GROUP_URL, RESOURCES, portalUrl, type AzureResource } from "./azure";

// Laid out in the style of the Azure Architecture Center: nested dashed boundaries, official icons with
// the product name underneath, numbered steps on the request path. Every resource is a link to the portal.

const ICON = 48;
const INK = "#14213d";
const MUTED = "#55657f";
const REQUEST = "#0047bb";
const INGEST = "#55657f";

const byName = (name: string): AzureResource => {
  const resource = RESOURCES.find((r) => r.name === name);
  if (!resource) throw new Error(`${name} is not in the deployed inventory`);
  return resource;
};

// Icon centers. Each entry must name a resource of the inventory.
const NODES: { name: string; x: number; y: number; note?: string }[] = [
  { name: "bcopilot-xxxxx-web", x: 305, y: 350 },
  { name: "bcopilot-xxxxx-safety-eastus2", x: 305, y: 530 },
  { name: "bcopilot-xxxxx-cosmos", x: 305, y: 660 },
  { name: "bcopilot-copilot-api", x: 545, y: 350 },
  { name: "bcopilot-mcp-bank", x: 725, y: 350, note: "ingress interno" },
  { name: "bcopilot-products-api", x: 990, y: 350 },
  { name: "bcopilot-customers-api", x: 1125, y: 350 },
  { name: "bcopilot-xxxxx-apim", x: 920, y: 190 },
  { name: "bcopilot-xxxxx-foundry", x: 625, y: 620 },
  { name: "bcopilot-xxxxx-search", x: 805, y: 620 },
  { name: "bcopilot-xxxxx-storage-events", x: 805, y: 785 },
  { name: "bcopilotxxxxxst", x: 625, y: 785 },
  { name: "bcopilot-xxxxx-ingest", x: 985, y: 785 },
  { name: "bcopilot-xxxxx-kv", x: 560, y: 940 },
  { name: "bcopilot-xxxxx-appi", x: 840, y: 940 },
  { name: "bcopilot-xxxxx-logs", x: 980, y: 940 },
  { name: "bcopilotxxxxxacr", x: 1120, y: 940 },
];

function Icon({ x, y, icon, size = ICON }: { x: number; y: number; icon: string; size?: number }) {
  return <image href={`/azure-icons/${icon}`} x={x - size / 2} y={y - size / 2} width={size} height={size} />;
}

function NodeLabel({ x, y, title, sub, note }: { x: number; y: number; title: string; sub: string; note?: string }) {
  return (
    <>
      <text x={x} y={y + 42} textAnchor="middle" fontSize={12.5} fontWeight={700} fill={INK}>
        {title}
      </text>
      <text x={x} y={y + 57} textAnchor="middle" fontSize={11} fill={MUTED}>
        {sub}
      </text>
      {note && (
        <text x={x} y={y + 72} textAnchor="middle" fontSize={11} fontWeight={600} fill="#5b3cc4">
          {note}
        </text>
      )}
    </>
  );
}

function PortalLink({ href, label, children }: { href: string; label: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" aria-label={label} className="group">
      {children}
    </a>
  );
}

function Highlight({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  return (
    <rect
      x={x}
      y={y}
      width={w}
      height={h}
      rx={10}
      className="fill-transparent transition-colors group-hover:fill-sky group-focus-visible:fill-sky"
    />
  );
}

function ResourceNode({ name, x, y, note }: { name: string; x: number; y: number; note?: string }) {
  const r = byName(name);
  return (
    <PortalLink href={portalUrl(r.type, r.name)} label={`Abrir ${r.name} en el portal de Azure`}>
      <Highlight x={x - 75} y={y - 32} w={150} h={note ? 112 : 98} />
      <Icon x={x} y={y} icon={r.icon} />
      <NodeLabel x={x} y={y} title={r.service} sub={r.name} note={note} />
    </PortalLink>
  );
}

function Boundary({
  x,
  y,
  w,
  h,
  stroke,
  dash = "6 4",
}: {
  x: number;
  y: number;
  w: number;
  h: number;
  stroke: string;
  dash?: string;
}) {
  return <rect x={x} y={y} width={w} height={h} rx={12} fill="none" stroke={stroke} strokeWidth={1.4} strokeDasharray={dash} />;
}

function Edge({ d, color = REQUEST }: { d: string; color?: string }) {
  return (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={1.6}
      markerEnd={color === REQUEST ? "url(#arrow-request)" : "url(#arrow-ingest)"}
    />
  );
}

function EdgeLabel({ x, y, children, anchor = "middle" }: { x: number; y: number; children: string; anchor?: "start" | "middle" | "end" }) {
  return (
    <text
      x={x}
      y={y}
      textAnchor={anchor}
      fontSize={11}
      fontWeight={600}
      fill="#33415c"
      stroke="white"
      strokeWidth={4}
      paintOrder="stroke"
      strokeLinejoin="round"
    >
      {children}
    </text>
  );
}

function Step({ x, y, label, ingest = false }: { x: number; y: number; label: string; ingest?: boolean }) {
  return (
    <g aria-hidden>
      <circle cx={x} cy={y} r={10} fill={ingest ? "white" : "#002a6e"} stroke="#002a6e" strokeWidth={1.5} />
      <text x={x} y={y + 4} textAnchor="middle" fontSize={11} fontWeight={700} fill={ingest ? "#002a6e" : "white"}>
        {label}
      </text>
    </g>
  );
}

const GROUP_URL = `${RESOURCE_GROUP_URL}/overview`;

export function ArchitectureDiagram() {
  const env = byName("bcopilot-xxxxx-env");
  return (
    <svg
      viewBox="0 0 1280 1050"
      role="group"
      aria-labelledby="arch-title"
      className="block h-auto w-full min-w-[1180px] font-sans xl:min-w-0"
    >
      <title id="arch-title">Diagrama de arquitectura del copiloto en Azure</title>
      <defs>
        <marker id="arrow-request" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 10 5 0 10z" fill={REQUEST} />
        </marker>
        <marker id="arrow-ingest" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 10 5 0 10z" fill={INGEST} />
        </marker>
      </defs>

      {/* Users sit outside the subscription. */}
      <Icon x={85} y={350} icon="users.svg" />
      <NodeLabel x={85} y={350} title="Asesor / Supervisor" sub="navegador" />

      <Boundary x={165} y={16} w={1100} h={1018} stroke="#8091ad" />
      <Icon x={191} y={38} icon="subscription.svg" size={20} />
      <text x={207} y={43} fontSize={13} fontWeight={700} fill={INK}>
        Suscripción Azure (Free Trial)
      </text>

      <Boundary x={185} y={60} w={1060} h={964} stroke="#8091ad" />
      <PortalLink href={GROUP_URL} label="Abrir el grupo de recursos bcopilot-rg en el portal de Azure">
        <Highlight x={197} y={68} w={232} h={28} />
        <Icon x={213} y={82} icon="resource-group.svg" size={20} />
        <text x={229} y={87} fontSize={13} fontWeight={700} fill={INK}>
          Grupo de recursos bcopilot-rg
        </text>
      </PortalLink>

      <Boundary x={205} y={104} w={200} h={620} stroke={REQUEST} dash="4 4" />
      <text x={221} y={128} fontSize={13} fontWeight={700} fill={REQUEST}>
        Región East US 2
      </text>

      <Boundary x={425} y={104} w={800} h={910} stroke={REQUEST} dash="4 4" />
      <text x={441} y={128} fontSize={13} fontWeight={700} fill={REQUEST}>
        Región Canada East
      </text>

      <Boundary x={445} y={255} w={760} h={225} stroke="#5b3cc4" />
      <PortalLink href={portalUrl(env.type, env.name)} label={`Abrir ${env.name} en el portal de Azure`}>
        <Highlight x={453} y={259} w={236} h={40} />
        <Icon x={472} y={279} icon={env.icon} size={26} />
        <text x={492} y={276} fontSize={12.5} fontWeight={700} fill={INK}>
          {env.service}
        </text>
        <text x={492} y={291} fontSize={11} fill={MUTED}>
          {env.name}
        </text>
      </PortalLink>

      <rect x={540} y={710} width={665} height={150} rx={12} fill="#f4f7fc" />
      <text x={556} y={732} fontSize={12.5} fontWeight={700} fill={INK}>
        Ingesta de documentos
      </text>

      <rect x={445} y={885} width={760} height={120} rx={12} fill="#f4f7fc" />
      <text x={461} y={905} fontSize={12.5} fontWeight={700} fill={INK}>
        Servicios transversales
      </text>

      {/* Request path */}
      <Edge d="M111 350H279" />
      <Step x={140} y={350} label="1" />
      <EdgeLabel x={205} y={338}>
        HTTPS
      </EdgeLabel>

      <Edge d="M331 350H519" />
      <Step x={355} y={350} label="2" />
      <EdgeLabel x={455} y={338}>
        HTTPS/SSE + JWT
      </EdgeLabel>

      <path d="M545 417V530H331" fill="none" stroke={REQUEST} strokeWidth={1.6} markerEnd="url(#arrow-request)" />
      <Edge d="M470 530V660H331" />
      <Edge d="M625 530V594" />
      <Edge d="M545 530H805V594" />
      <EdgeLabel x={585} y={522}>
        REST
      </EdgeLabel>
      <Step x={372} y={530} label="3" />
      <Step x={700} y={530} label="4" />
      <Step x={470} y={600} label="5" />

      <Edge d="M571 350H699" />
      <Step x={590} y={350} label="6" />
      <EdgeLabel x={648} y={333}>
        MCP streamable HTTP
      </EdgeLabel>

      <Edge d="M725 324V190H894" />
      <Step x={725} y={230} label="7" />
      <EdgeLabel x={745} y={180} anchor="start">
        REST + subscription key
      </EdgeLabel>
      <Edge d="M946 190H990V324" />
      <Edge d="M990 190H1125V324" />
      <EdgeLabel x={1060} y={180}>
        REST + X-Backend-Secret
      </EdgeLabel>

      {/* Ingestion path */}
      <Edge d="M651 785H779" color={INGEST} />
      <Step x={680} y={785} label="A" ingest />
      <EdgeLabel x={735} y={773}>
        BlobCreated
      </EdgeLabel>
      <Edge d="M831 785H959" color={INGEST} />
      <Step x={860} y={785} label="B" ingest />
      <EdgeLabel x={915} y={773}>
        Event Grid
      </EdgeLabel>
      <Edge d="M985 759V620H831" color={INGEST} />
      <Step x={985} y={700} label="C" ingest />
      <EdgeLabel x={999} y={668} anchor="start">
        indexación
      </EdgeLabel>

      {NODES.map((node) => (
        <ResourceNode key={node.name} {...node} />
      ))}

      {/* The six user-assigned identities have no single portal page; the node opens the resource group. */}
      <PortalLink href={GROUP_URL} label="Abrir las identidades administradas del grupo bcopilot-rg en el portal de Azure">
        <Highlight x={625} y={908} w={150} h={98} />
        <Icon x={700} y={940} icon="managed-identities.svg" />
        <NodeLabel x={700} y={940} title="Managed Identities" sub="6 asignadas por el usuario" />
      </PortalLink>
    </svg>
  );
}
