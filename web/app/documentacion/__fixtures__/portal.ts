import { vi } from "vitest";
import fixture from "./inventory.json";

/** Stubs fetch as Static Web Apps answers it: /.auth/me with or without the owner role, the private inventory,
 * and every other request (the API status probe) left pending. */
export function stubSession(owner: boolean) {
  const fetchMock = vi.fn((url: string) => {
    if (url === "/.auth/me") {
      const clientPrincipal = owner ? { userRoles: ["anonymous", "authenticated", "owner"] } : null;
      return Promise.resolve(Response.json({ clientPrincipal }));
    }
    if (url === "/privado/inventario.json") {
      return Promise.resolve(owner ? Response.json(fixture) : new Response(null, { status: 401 }));
    }
    return new Promise(() => {});
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}
