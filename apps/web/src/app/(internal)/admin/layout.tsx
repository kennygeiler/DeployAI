import type { Metadata } from "next"
import type { ReactNode } from "react"

export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
}

export default function InternalAdminLayout({ children }: { children: ReactNode }) {
  return <div className="min-h-dvh">{children}</div>
}
