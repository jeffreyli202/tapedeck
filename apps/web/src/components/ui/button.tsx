import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-md text-sm font-medium transition-colors disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-accent cursor-pointer",
  {
    variants: {
      variant: {
        default: "bg-accent text-black hover:bg-accent/90",
        outline: "border border-border bg-transparent hover:bg-panel-2",
        ghost: "hover:bg-panel-2",
        buy: "bg-up text-white hover:bg-up/90",
        sell: "bg-down text-white hover:bg-down/90",
        destructive: "bg-down/15 text-down hover:bg-down/25",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-7 px-2.5 text-xs",
        icon: "h-8 w-8",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
