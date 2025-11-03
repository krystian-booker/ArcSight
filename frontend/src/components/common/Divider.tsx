/**
 * Divider component for visual separation
 */

interface DividerProps {
  className?: string;
  label?: string;
}

export default function Divider({ className = '', label }: DividerProps) {
  if (label) {
    return (
      <div className={`flex items-center gap-md ${className}`}>
        <hr className="divider flex-1" />
        <span className="text-xs uppercase tracking-arc text-arc-subtle">{label}</span>
        <hr className="divider flex-1" />
      </div>
    );
  }

  return <hr className={`divider ${className}`} />;
}
