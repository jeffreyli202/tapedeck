import type { Metadata } from "next";
import type { ReactNode } from "react";

import { Nav } from "@/components/nav";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "TapeDeck",
  description: "Rewind the market. Trade it again.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">
        <Providers>
          <Nav />
          <main className="mx-auto max-w-[1800px] px-4 py-4">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
