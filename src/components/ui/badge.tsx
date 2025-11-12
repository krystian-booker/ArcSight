import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-[var(--color-primary)] text-white shadow hover:bg-[var(--color-primary)]/80",
        secondary:
          "border-transparent bg-[var(--color-surface-alt)] text-[var(--color-text)] hover:bg-[var(--color-panel)]",
        destructive:
          "border-transparent bg-[var(--color-danger)] text-white shadow hover:bg-[var(--color-danger)]/80",
        success:
          "border-transparent bg-[var(--color-success)] text-white shadow hover:bg-[var(--color-success)]/80",
        warning:
          "border-transparent bg-[var(--color-warning)] text-white shadow hover:bg-[var(--color-warning)]/80",
        outline: "text-[var(--color-text)] border-[var(--color-border-strong)]",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
