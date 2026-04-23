import type { Metadata } from "next";
import { IBM_Plex_Mono, Inter } from "next/font/google";
import "./globals.css";
import { AxeDev } from "./axe-dev";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-ibm-plex-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "DeployAI — initializing",
  description: "DeployAI web scaffold. Feature surfaces land progressively.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${inter.variable} ${ibmPlexMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        {/* Skip-to-content link — WCAG 2.4.1 Bypass Blocks. Visually
            hidden until focused; jumps keyboard users past any future
            header/nav chrome directly to the <main> landmark on `/`.
            Every surface inherits this from the root layout. */}
        <a
          href="#main"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground focus:shadow"
        >
          Skip to main content
        </a>
        {children}
        <AxeDev />
      </body>
    </html>
  );
}
