import { portalUrl, resourceByKey, type AzureResource, type Deployment, type ResourceKey } from "./azure";

// Laid out in the style of the Azure Architecture Center: nested dashed boundaries, official icons with
// the product name underneath, numbered steps on the request path. Every resource is a link to the portal.

const ICON = 48;
const INK = "#14213d";
const MUTED = "#55657f";
const REQUEST = "#0047bb";
const INGEST = "#55657f";

// Icon centers. The left column is one region box and everything else the other.
const LEFT_REGION: ResourceKey[] = ["web", "content-safety", "cosmos"];
const NODES: { key: ResourceKey; x: number; y: number; note?: string }[] = [
  { key: "web", x: 305, y: 350 },
  { key: "content-safety", x: 305, y: 530 },
  { key: "cosmos", x: 305, y: 660 },
  { key: "copilot-api", x: 545, y: 350 },
  { key: "mcp-bank", x: 725, y: 350, note: "ingress interno" },
  { key: "products-api", x: 990, y: 350 },
  { key: "customers-api", x: 1125, y: 350 },
  { key: "apim", x: 920, y: 190 },
  { key: "foundry", x: 625, y: 620 },
  { key: "search", x: 805, y: 620 },
  { key: "storage-events", x: 805, y: 785 },
  { key: "storage", x: 625, y: 785 },
  { key: "ingest", x: 985, y: 785 },
  { key: "key-vault", x: 560, y: 940 },
  { key: "app-insights", x: 840, y: 940 },
  { key: "log-analytics", x: 980, y: 940 },
  { key: "container-registry", x: 1120, y: 940 },
];

// The layout draws two region boxes; a deployment that spreads differently would be drawn wrong.
function regionLabels(deployment: Deployment): { left: string; right: string } {
  const left = resourceByKey(deployment, "web").location;
  const right = resourceByKey(deployment, "copilot-api").location;
  for (const r of deployment.resources) {
    const expected = LEFT_REGION.includes(r.key) ? left : right;
    if (r.location !== expected) throw new Error(`diagram: ${r.key} is in ${r.location}, the layout expects ${expected}`);
  }
  return { left: resourceByKey(deployment, "web").regionLabel, right: resourceByKey(deployment, "copilot-api").regionLabel };
}

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

function ResourceNode({
  deployment,
  r,
  x,
  y,
  note,
}: {
  deployment: Deployment;
  r: AzureResource;
  x: number;
  y: number;
  note?: string;
}) {
  return (
    <PortalLink href={portalUrl(deployment, r)} label={`Abrir ${r.name} en el portal de Azure`}>
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

export function ArchitectureDiagram({ deployment }: { deployment: Deployment }) {
  const env = resourceByKey(deployment, "container-apps-env");
  const regions = regionLabels(deployment);
  const group = deployment.resourceGroup;
  const groupUrl = `${deployment.resourceGroupUrl}/overview`;
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
      <PortalLink href={groupUrl} label={`Abrir el grupo de recursos ${group} en el portal de Azure`}>
        <Highlight x={197} y={68} w={232} h={28} />
        <Icon x={213} y={82} icon="resource-group.svg" size={20} />
        <text x={229} y={87} fontSize={13} fontWeight={700} fill={INK}>
          Grupo de recursos {group}
        </text>
      </PortalLink>

      <Boundary x={205} y={104} w={200} h={620} stroke={REQUEST} dash="4 4" />
      <text x={221} y={128} fontSize={13} fontWeight={700} fill={REQUEST}>
        Región {regions.left}
      </text>

      <Boundary x={425} y={104} w={800} h={910} stroke={REQUEST} dash="4 4" />
      <text x={441} y={128} fontSize={13} fontWeight={700} fill={REQUEST}>
        Región {regions.right}
      </text>

      <Boundary x={445} y={255} w={760} h={225} stroke="#5b3cc4" />
      <PortalLink href={portalUrl(deployment, env)} label={`Abrir ${env.name} en el portal de Azure`}>
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

      {NODES.map(({ key, ...position }) => (
        <ResourceNode key={key} deployment={deployment} r={resourceByKey(deployment, key)} {...position} />
      ))}

      {/* The six user-assigned identities have no single portal page; the node opens the resource group. */}
      <PortalLink href={groupUrl} label={`Abrir las identidades administradas del grupo ${group} en el portal de Azure`}>
        <Highlight x={625} y={908} w={150} h={98} />
        <Icon x={700} y={940} icon="managed-identities.svg" />
        <NodeLabel x={700} y={940} title="Managed Identities" sub="6 asignadas por el usuario" />
      </PortalLink>
    </svg>
  );
}
