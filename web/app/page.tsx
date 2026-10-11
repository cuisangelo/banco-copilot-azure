"use client";

import { Chat } from "@/components/Chat";
import { useSession } from "@/lib/session";

export default function AdvisorPage() {
  const { session } = useSession();
  // A new persona starts a new copilot session: resume and escalation decisions are bound to the sub that started it.
  return (
    <main className="flex min-h-0 flex-1 flex-col">
      <Chat key={session?.persona ?? "none"} />
    </main>
  );
}
