/**
 * Panel/Card component for content containers
 */

import type { HTMLAttributes, ReactNode } from 'react';

interface PanelProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  children: ReactNode;
  title?: string | ReactNode;
  actions?: ReactNode;
  noPadding?: boolean;
}

export default function Panel({
  children,
  title,
  actions,
  noPadding = false,
  className = '',
  ...props
}: PanelProps) {
  return (
    <div
      className={`
        rounded-arc-lg panel-inset
        ${className}
      `}
      {...props}
    >
      {title && (
        <div className="flex items-center justify-between border-b border-arc-border px-lg py-md">
          {typeof title === 'string' ? (
            <h3 className="text-base font-semibold uppercase tracking-arc-wider text-arc-accent">{title}</h3>
          ) : (
            title
          )}
          {actions && <div className="flex items-center gap-xs">{actions}</div>}
        </div>
      )}
      <div className={noPadding ? '' : 'p-lg'}>{children}</div>
    </div>
  );
}
