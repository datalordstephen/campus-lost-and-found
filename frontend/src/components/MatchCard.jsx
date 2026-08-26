// A match is a pairing: a photograph on one side, the words someone typed on
// the other. This renders that literally — the two halves with a seam between
// them, and the strength of the match marked along the seam.
import { imageUrl } from "../api/client";
import { Thumbnail, formatDate } from "./ItemCard";
import { cx, labelForStatus, lot, stampFor, theme } from "../theme";

/**
 * Where each candidate sits on the seam, as a fraction of the track.
 *
 * Raw CLIP cosine for a *correct* image/text pair is roughly 0.22-0.33 when
 * matching words against a bare photograph, and higher once the found item
 * carries a description of its own. Either way it is nowhere near 1.0, so
 * printing it as "29% match" on a perfect hit reads as broken.
 *
 * A softmax was the first attempt and it collapsed: at any useful temperature
 * the best candidate takes ~97% of the weight and every other marker piles up
 * against the left edge, which tells the reader nothing about ranks 2..k.
 * Min-max across the returned set spreads them out instead, and answers the
 * only question a top-k list can answer — how close is this one to the best
 * one we found?
 */
export function relativeConfidence(scores) {
  if (!scores.length) return [];
  const best = Math.max(...scores);
  const worst = Math.min(...scores);
  const span = best - worst;
  // A single result, or a dead heat, sits at the top of the track.
  if (span < 1e-6) return scores.map(() => 0.95);
  return scores.map((s) => 0.15 + 0.8 * ((s - worst) / span));
}

export default function MatchCard({ match, kind, rank, confidence = 0, onClaim, index = 0 }) {
  const { item, score } = match;
  const src = imageUrl(item.image_path);
  const words = item.description || (kind === "found" ? "Unlabelled item" : "Lost item");
  const place = kind === "found" ? item.location : item.location_last_seen;
  const isTop = rank === 1;

  return (
    <article
      className={cx(theme.card, "rise")}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className={theme.meta}>{lot(kind, item.id)}</span>
        <span className={stampFor(item.status)}>{labelForStatus(item.status)}</span>
      </div>

      {/* The seam: photograph -> strength -> words. */}
      <div className="mt-4 flex items-stretch gap-4">
        <Thumbnail src={src} alt={words} className="h-24 w-24 sm:h-28 sm:w-28" />

        <div className="flex min-w-0 flex-1 flex-col justify-between py-0.5">
          <Seam confidence={confidence} score={score} isTop={isTop} delay={index * 70} />

          <div className="mt-3 min-w-0">
            <p className={cx(theme.heading.card, "line-clamp-2")}>{words}</p>
            <p className={cx(theme.figure, "mt-1.5")}>
              {place ? `${place} / ` : ""}
              {formatDate(item.created_at)}
            </p>
          </div>
        </div>
      </div>

      {onClaim && (
        <div className="mt-4 flex items-center justify-between gap-3">
          <span className={theme.text.tiny}>
            {isTop ? "Closest match to your description" : `Ranked ${rank} of the results`}
          </span>
          <button onClick={onClaim} className={cx(theme.button.primary, theme.button.small)}>
            This is mine
          </button>
        </div>
      )}
    </article>
  );
}

/**
 * The strength track. The marker's position is the candidate's share of the
 * returned confidence; the raw cosine sits beside it for anyone who wants the
 * real number (and for the evaluation write-up).
 */
function Seam({ confidence, score, isTop, delay }) {
  const pct = Math.min(96, Math.max(4, confidence * 100));

  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className={isTop ? theme.metaInk : theme.meta}>
          {isTop ? "strongest" : "candidate"}
        </span>
        <span className={theme.figure}>cos {score.toFixed(3)}</span>
      </div>

      <div className="relative mt-2.5 h-3">
        {/* the track */}
        <div
          className="seam-track absolute top-1/2 h-px w-full -translate-y-1/2 bg-line"
          style={{ animationDelay: `${delay}ms` }}
        />
        {/* the marker */}
        <span
          className={cx(
            "seam-mark absolute top-1/2 block h-2.5 w-2.5 rounded-full",
            isTop ? "bg-ink" : "border border-ash bg-paper",
          )}
          style={{ left: `${pct}%`, animationDelay: `${delay + 420}ms` }}
        />
      </div>
    </div>
  );
}
