import { PortalProvider } from "./portal";

export default function DocumentationLayout({ children }: { children: React.ReactNode }) {
  return <PortalProvider>{children}</PortalProvider>;
}
