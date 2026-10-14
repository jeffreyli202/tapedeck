"use client";

import { useQuery } from "@tanstack/react-query";
import { Disc3 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { api, setToken } from "@/lib/api";
import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Sessions" },
  { href: "/backtest", label: "Backtest" },
  { href: "/analytics", label: "Analytics" },
  { href: "/journal", label: "Journal" },
];

export function Nav() {
  const pathname = usePathname();
  const { data: auth } = useQuery({ queryKey: ["auth-config"], queryFn: () => api<{ auth_enabled: boolean }>("/auth/config") });
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ user: string }>("/auth/me"),
    enabled: !!auth?.auth_enabled && pathname !== "/login",
  });

  return (
    <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-[1800px] items-center gap-6 px-4">
        <Link href="/" className="flex items-center gap-2 font-semibold tracking-tight">
          <Disc3 className="h-5 w-5 text-accent" />
          TapeDeck
          <span className="hidden text-xs font-normal text-muted md:inline">Rewind the market. Trade it again.</span>
        </Link>
        <nav className="flex gap-1">
          {LINKS.map((l) => {
            const active = l.href === "/" ? pathname === "/" || pathname.startsWith("/replay") : pathname.startsWith(l.href);
            return (
              <Link
                key={l.href}
                href={l.href}
                className={cn(
                  "rounded-md px-3 py-1.5 text-sm text-muted hover:text-foreground",
                  active && "bg-panel-2 text-foreground",
                )}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        {auth?.auth_enabled && me && (
          <div className="ml-auto flex items-center gap-3 text-sm text-muted">
            {me.user}
            <button
              className="hover:text-foreground"
              onClick={() => {
                setToken(null);
                window.location.href = "/login";
              }}
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
