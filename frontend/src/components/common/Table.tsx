/**
 * Table component with consistent styling
 */

import type { ReactNode, TableHTMLAttributes } from 'react';

interface TableProps extends TableHTMLAttributes<HTMLTableElement> {
  children: ReactNode;
}

interface TableHeaderProps {
  children: ReactNode;
}

interface TableBodyProps {
  children: ReactNode;
}

interface TableRowProps {
  children: ReactNode;
  className?: string;
}

interface TableHeadProps {
  children: ReactNode;
  className?: string;
}

interface TableCellProps {
  children: ReactNode;
  className?: string;
}

export function Table({ children, className = '', ...props }: TableProps) {
  return (
    <div className="overflow-hidden rounded-arc-md border border-white/5">
      <table
        className={`
          w-full border-separate border-spacing-0
          ${className}
        `}
        style={{
          background: 'rgba(30, 30, 30, 0.95)'
        }}
        {...props}
      >
        {children}
      </table>
    </div>
  );
}

export function TableHeader({ children }: TableHeaderProps) {
  return (
    <thead
      style={{
        background: 'rgba(23, 23, 23, 0.8)'
      }}
    >
      {children}
    </thead>
  );
}

export function TableBody({ children }: TableBodyProps) {
  return <tbody>{children}</tbody>;
}

export function TableRow({ children, className = '' }: TableRowProps) {
  return (
    <tr
      className={`
        transition-colors duration-arc-fast
        hover:bg-arc-teal/6
        ${className}
      `}
    >
      {children}
    </tr>
  );
}

export function TableHead({ children, className = '' }: TableHeadProps) {
  return (
    <th
      className={`
        px-4 py-3 text-left text-[0.85rem] font-medium
        uppercase tracking-arc text-arc-accent
        border-b border-white/6
        ${className}
      `}
    >
      {children}
    </th>
  );
}

export function TableCell({ children, className = '' }: TableCellProps) {
  return (
    <td
      className={`
        px-4 py-3 text-[0.85rem] text-arc-text
        border-b border-white/6
        last:border-b-0
        ${className}
      `}
    >
      {children}
    </td>
  );
}

// Export as default with sub-components
const TableWithSubComponents = Object.assign(Table, {
  Header: TableHeader,
  Body: TableBody,
  Row: TableRow,
  Head: TableHead,
  Cell: TableCell,
});

export default TableWithSubComponents;
