import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const tones = {
  neutral: "bg-panel-2 text-muted",
  up: "bg-up/15 text-up",
  down: "bg-down/15 text-down",
  accent: "bg-accent/15 text-accent",
};

export function Badge({
  tone = "neutral",
  className,
  ...props
}: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium", tones[tone], className)}
      {...props}
    />
  );
}
