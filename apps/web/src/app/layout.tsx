import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DeployAI — initializing",
  description:
    "DeployAI web scaffold. Feature surfaces (Digest, In-Meeting, Phase Tracking) land in Stories 1.4+.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
