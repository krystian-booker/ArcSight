/**
 * Badge component for status indicators and tags
 */

import type { ReactNode } from 'react';

type BadgeVariant = 'default' | 'success' | 'warning' | 'danger' | 'info';
type BadgeSize = 'sm' | 'md' | 'lg';

interface BadgeProps {
  children: ReactNode;
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
  className?: string;
}

const variantStyles: Record<BadgeVariant, string> = {
  default: 'bg-arc-surface-alt text-arc-text border-arc-border-strong',
  success: 'bg-arc-success/12 text-arc-success border-arc-success/35',
  warning: 'bg-arc-warning/12 text-arc-warning border-arc-warning/35',
  danger: 'bg-arc-danger/12 text-arc-danger border-arc-danger/35',
  info: 'bg-arc-teal/12 text-arc-teal border-arc-teal/35',
};

const dotColors: Record<BadgeVariant, string> = {
  default: 'bg-arc-muted',
  success: 'bg-arc-success',
  warning: 'bg-arc-warning',
  danger: 'bg-arc-danger',
  info: 'bg-arc-teal',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-2 py-1 text-[0.7rem]',
  md: 'px-[0.65rem] py-[0.25rem] text-[0.75rem]',
  lg: 'px-3 py-1.5 text-sm',
};

export default function Badge({
  children,
  variant = 'default',
  size = 'md',
  dot = false,
  className = '',
}: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center gap-2xs
        rounded-full font-medium uppercase tracking-arc
        badge-bordered
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full glow-dot ${dotColors[variant]}`} />}
      {children}
    </span>
  );
}
