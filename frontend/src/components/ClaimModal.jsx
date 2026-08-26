// Where a claimant proves the item is theirs by recalling the detail they
// recorded when they filed the report.
import { useEffect, useState } from "react";
import { Spinner } from "./Spinner";
import { cx, lot, theme } from "../theme";

export default function ClaimModal({ open, match, attemptsLeft, onClose, onSubmit }) {
  const [description, setDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (open) {
      setDescription("");
      setSubmitting(false);
    }
  }, [open]);

  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && !submitting && onClose();
    if (open) window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose, submitting]);

  if (!open) return null;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!description.trim() || submitting) return;
    setSubmitting(true);
    try {
      await onSubmit(description.trim());
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className={theme.modal.backdrop} onClick={() => !submitting && onClose()}>
      <div className={theme.modal.panel} onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <span className={theme.meta}>{lot("found", match?.item?.id)}</span>
            <h2 className={cx(theme.display.md, "mt-2")}>Prove it&rsquo;s yours</h2>
          </div>
          <button
            onClick={onClose}
            disabled={submitting}
            className="u-meta pt-1 text-mist transition-colors duration-150 hover:text-ink"
          >
            close
          </button>
        </div>

        <p className={cx(theme.text.muted, "mt-3")}>
          Describe the private detail you recorded when you reported this item. It is checked
          against your original report — nobody at the desk reads it.
        </p>

        <form onSubmit={handleSubmit} className="mt-6">
          <label htmlFor="claim-description" className={theme.label}>
            The detail
          </label>
          <textarea
            id="claim-description"
            rows={4}
            autoFocus
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="A blue sticker under the lid, and the handle is scratched"
            className={cx(theme.input, "resize-none")}
          />

          {typeof attemptsLeft === "number" && (
            <p
              className={cx(
                "mt-3 font-mono text-xs tabular-nums",
                attemptsLeft <= 1 ? "text-alert" : "text-mist",
              )}
            >
              {attemptsLeft} {attemptsLeft === 1 ? "attempt" : "attempts"} left on this item
            </p>
          )}

          <div className="mt-6 flex gap-2">
            <button
              type="submit"
              disabled={!description.trim() || submitting}
              className={cx(theme.button.primary, "flex-1")}
            >
              {submitting && <Spinner />}
              {submitting ? "Checking" : "Submit claim"}
            </button>
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className={theme.button.secondary}
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
