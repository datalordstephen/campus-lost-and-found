import { cx, theme } from "../theme";

/** Ink arc on a hairline ring — no icon dependency, matches the mono chrome. */
export function Spinner({ size = 14, className }) {
  return (
    <span
      role="status"
      aria-label="Working"
      className={cx("inline-block shrink-0 animate-spin rounded-full", className)}
      style={{
        width: size,
        height: size,
        border: "1.5px solid currentColor",
        borderTopColor: "transparent",
        opacity: 0.9,
      }}
    />
  );
}

export function SkeletonList({ rows = 3 }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className={cx(theme.cardFlat, "flex gap-4")}>
          <div className={cx(theme.skeleton, "h-[4.5rem] w-[4.5rem] shrink-0")} />
          <div className="flex-1 space-y-2.5 py-1.5">
            <div className={cx(theme.skeleton, "h-2.5 w-24")} />
            <div className={cx(theme.skeleton, "h-3.5 w-2/3")} />
            <div className={cx(theme.skeleton, "h-2.5 w-1/3")} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** An empty screen is an invitation to act, so it always names the next step. */
export function EmptyState({ title, hint }) {
  return (
    <div className={theme.empty}>
      <p className="text-sm font-500 text-ink">{title}</p>
      {hint && <p className="mx-auto mt-1.5 max-w-xs text-sm leading-relaxed text-mist">{hint}</p>}
    </div>
  );
}
