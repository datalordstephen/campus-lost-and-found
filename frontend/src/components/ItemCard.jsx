// One object in the property office: its photograph, its lot number, its marking.
import { imageUrl } from "../api/client";
import { cx, labelForStatus, lot, stampFor, theme } from "../theme";

export default function ItemCard({ item, kind, actions, className }) {
  const src = imageUrl(item.image_path);
  const title = item.description || (kind === "found" ? "Unlabelled item" : "Lost item");
  const place = kind === "found" ? item.location : item.location_last_seen;

  return (
    <article className={cx(theme.card, className)}>
      <div className="flex gap-4">
        <Thumbnail src={src} alt={title} />

        <div className="min-w-0 flex-1">
          <div className="flex items-center justify-between gap-3">
            <span className={theme.meta}>{lot(kind, item.id)}</span>
            <span className={stampFor(item.status)}>{labelForStatus(item.status)}</span>
          </div>

          <h3 className={cx(theme.heading.card, "mt-2.5")}>{title}</h3>

          <p className={cx(theme.figure, "mt-2 flex flex-wrap items-center gap-x-2 gap-y-1")}>
            {place && <span>{place}</span>}
            {place && <span className="text-line">/</span>}
            <span>{formatDate(item.created_at)}</span>
          </p>
        </div>
      </div>

      {actions && <div className="mt-4 flex flex-wrap items-center gap-2">{actions}</div>}
    </article>
  );
}

/**
 * The photograph is the only colour on the page, so it gets a clean square and
 * nothing else — no frame, no overlay, no rounded-away corners.
 */
export function Thumbnail({ src, alt, className = "h-[4.5rem] w-[4.5rem]" }) {
  if (!src) {
    return (
      <div className={cx(className, "grid shrink-0 place-items-center rounded-md bg-ground")}>
        <span className="u-meta text-mist">no photo</span>
      </div>
    );
  }
  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      className={cx(className, "shrink-0 rounded-md bg-ground object-cover")}
    />
  );
}

export function formatDate(value) {
  if (!value) return "";
  // The API emits naive UTC; mark it so it renders in the reader's local time.
  const iso = /[Zz]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";

  const minutes = Math.round((Date.now() - date.getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} hr ago`;
  if (minutes < 10080) return `${Math.round(minutes / 1440)} days ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}
