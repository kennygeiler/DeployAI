import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Admin — Runs",
  description: "Ingestion-run observability. Stub route; Story 1.16 ships the full admin shell.",
};

export default function AdminRunsStub() {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="flex flex-1 flex-col items-start gap-6 p-16 outline-none"
    >
      <h1 className="text-display font-semibold tracking-tight text-ink-950">Admin — Runs</h1>
      <p className="max-w-xl text-body text-ink-600">
        This is a Story 1.7 stub so the docker-compose smoke gate can verify the route renders
        without error. Story 1.16 replaces this with the real admin shell once AuthzResolver (Story
        2.1) lands.
      </p>
      <p className="max-w-xl text-small text-ink-400">
        Until then, runs observability lives in CI artifacts and control-plane logs.
      </p>
    </main>
  );
}
