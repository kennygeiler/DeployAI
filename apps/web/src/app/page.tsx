import Link from "next/link";

const surfaces = [
  { href: "/digest", label: "Morning digest" },
  { href: "/phase-tracking", label: "Phase & task tracking" },
  { href: "/evening", label: "Evening synthesis" },
] as const;

export default function Home() {
  return (
    <main
      id="main"
      tabIndex={-1}
      className="flex flex-1 flex-col items-center justify-center gap-6 p-16 text-center outline-none"
    >
      <h1 className="text-display font-semibold tracking-tight text-ink-950">
        DeployAI — initializing
      </h1>
      <p className="max-w-md text-body text-ink-600">
        Feature surfaces: strategist preview routes (set{" "}
        <code className="text-body bg-paper-200 rounded px-1">x-deployai-role</code> to enter).
      </p>
      <ul className="text-body text-evidence-800 flex max-w-sm flex-col gap-2 text-left">
        {surfaces.map((s) => (
          <li key={s.href}>
            <Link
              className="font-medium underline-offset-2 hover:underline focus-visible:ring-ring focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
              href={s.href}
            >
              {s.label}
            </Link>
            <span className="text-ink-500 text-sm"> — {s.href}</span>
          </li>
        ))}
      </ul>
    </main>
  );
}
