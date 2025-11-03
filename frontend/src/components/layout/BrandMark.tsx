/**
 * Animated brand logo with gradient pips
 */

export default function BrandMark() {
  return (
    <div className="group grid grid-cols-3 gap-[5px] rounded-arc-md bg-arc-teal/10 p-xs shadow-[inset_0_0_0_1px_rgba(0,194,168,0.2)]">
      {[...Array(9)].map((_, i) => (
        <div
          key={i}
          className="h-3 w-3 rounded-[3px] transition-transform duration-arc ease-arc-out group-hover:-translate-y-0.5"
          style={{
            background: 'linear-gradient(135deg, rgba(212, 46, 18, 0.85), rgba(0, 194, 168, 0.8))',
          }}
        />
      ))}
    </div>
  );
}
