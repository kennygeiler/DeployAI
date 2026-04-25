import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AdminToaster } from "@/components/internal/AdminToaster";

export const metadata: Metadata = {
  title: "Admin",
  robots: { index: false, follow: false },
};

export default function InternalAdminLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-dvh">
      {children}
      <AdminToaster />
    </div>
  );
}
