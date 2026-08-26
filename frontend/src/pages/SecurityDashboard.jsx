// The property desk: take custody of what comes in, and release what is proven.
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import ItemCard from "../components/ItemCard";
import MatchCard, { relativeConfidence } from "../components/MatchCard";
import { EmptyState, SkeletonList, Spinner } from "../components/Spinner";
import { useToast } from "../components/Toast";
import { cx, labelForStatus, lot, stampFor, theme } from "../theme";

const TABS = [
  {
    id: "custody",
    label: "Incoming",
    heading: "What came in",
    lead: "Confirm each item is physically at your post, then find who is looking for it.",
  },
  {
    id: "claims",
    label: "Claims",
    heading: "Who is claiming",
    lead: "Every claim here has been checked against the owner's own record of the item.",
  },
];

export default function SecurityDashboard() {
  const toast = useToast();
  const [tab, setTab] = useState("custody");
  const current = TABS.find((t) => t.id === tab);

  return (
    <div>
      <header>
        <span className={theme.meta}>Property desk</span>
        <h1 className={cx(theme.heading.page, "mt-3")}>{current.heading}</h1>
        <p className={cx(theme.text.lead, "mt-4 max-w-md")}>{current.lead}</p>
      </header>

      <nav className={cx(theme.tab.row, "mt-10")}>
        {TABS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={tab === id ? theme.tab.itemActive : theme.tab.item}
          >
            {label}
          </button>
        ))}
      </nav>

      <div className="mt-8">
        {tab === "custody" && <Custody toast={toast} />}
        {tab === "claims" && <ClaimQueue toast={toast} />}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function Custody({ toast }) {
  const [items, setItems] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [openId, setOpenId] = useState(null);

  const load = useCallback(() => {
    api.listFound().then(setItems).catch((err) => {
      toast.error(errorMessage(err, "Could not load items"));
      setItems([]);
    });
  }, [toast]);

  useEffect(load, [load]);

  const confirm = async (id) => {
    setBusyId(id);
    try {
      await api.confirmCustody(id);
      toast.success(`${lot("found", id)} confirmed at your post.`);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Could not confirm custody"));
    } finally {
      setBusyId(null);
    }
  };

  if (items === null) return <SkeletonList />;
  if (items.length === 0) {
    return (
      <div className={theme.cardFlat}>
        <EmptyState title="Nothing has been handed in" hint="Items logged by students appear here." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div key={item.id}>
          <ItemCard
            item={item}
            kind="found"
            actions={
              <>
                {item.status === "pending_custody" && (
                  <button
                    onClick={() => confirm(item.id)}
                    disabled={busyId === item.id}
                    className={cx(theme.button.primary, theme.button.small)}
                  >
                    {busyId === item.id && <Spinner />}
                    Confirm custody
                  </button>
                )}
                <button
                  onClick={() => setOpenId(openId === item.id ? null : item.id)}
                  className={cx(theme.button.secondary, theme.button.small)}
                >
                  {openId === item.id ? "Hide owners" : "Find the owner"}
                </button>
              </>
            }
          />
          {openId === item.id && <PossibleOwners foundItemId={item.id} toast={toast} />}
        </div>
      ))}
    </div>
  );
}

function PossibleOwners({ foundItemId, toast }) {
  const [matches, setMatches] = useState(null);

  useEffect(() => {
    api.matchesForFound(foundItemId).then(setMatches).catch((err) => {
      toast.error(errorMessage(err, "Could not load possible owners"));
      setMatches([]);
    });
  }, [foundItemId, toast]);

  const confidences = matches ? relativeConfidence(matches.map((m) => m.score)) : [];

  return (
    <div className="mt-3 space-y-3 border-l border-line pl-4 md:ml-6">
      {matches === null ? (
        <SkeletonList rows={2} />
      ) : matches.length === 0 ? (
        <div className={theme.cardFlat}>
          <EmptyState title="No open report describes this item" />
        </div>
      ) : (
        <>
          <p className={theme.meta}>Open reports that resemble it</p>
          {matches.map((m, i) => (
            <MatchCard
              key={m.item.id} match={m} kind="lost" rank={i + 1} index={i}
              confidence={confidences[i]}
            />
          ))}
        </>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
const FILTERS = ["approved", "rejected", "released", "all"];

function ClaimQueue({ toast }) {
  const [claims, setClaims] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [filter, setFilter] = useState("approved");

  const load = useCallback(() => {
    setClaims(null);
    api
      .listClaims(filter === "all" ? {} : { status: filter })
      .then(setClaims)
      .catch((err) => {
        toast.error(errorMessage(err, "Could not load claims"));
        setClaims([]);
      });
  }, [filter, toast]);

  useEffect(load, [load]);

  const release = async (id) => {
    setBusyId(id);
    try {
      await api.releaseClaim(id);
      toast.success("Released. The student who handed it in has been credited.");
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Could not release the item"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <div className="flex gap-1.5 overflow-x-auto pb-1">
        {FILTERS.map((value) => (
          <button
            key={value}
            onClick={() => setFilter(value)}
            className={cx(theme.chip.base, filter === value ? theme.chip.on : theme.chip.off)}
          >
            {value}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-3">
        {claims === null ? (
          <SkeletonList rows={2} />
        ) : claims.length === 0 ? (
          <div className={theme.cardFlat}>
            <EmptyState title={`No ${filter === "all" ? "" : filter} claims`.replace("  ", " ")} />
          </div>
        ) : (
          claims.map((claim) => (
            <article key={claim.id} className={theme.card}>
              <div className="flex items-center justify-between gap-3">
                <span className={theme.meta}>
                  {lot("found", claim.found_item_id)} &nbsp;/&nbsp; {lot("lost", claim.lost_item_id)}
                </span>
                <span className={stampFor(claim.status)}>{labelForStatus(claim.status)}</span>
              </div>

              <blockquote className={cx(theme.well, "mt-4")}>
                <p className="text-sm leading-relaxed text-ink">
                  &ldquo;{claim.claimant_description}&rdquo;
                </p>
                <p className={cx(theme.figure, "mt-2.5")}>claimant #{claim.claimant_id}</p>
              </blockquote>

              <Entailment score={claim.nli_score} />

              {claim.status === "approved" && (
                <button
                  onClick={() => release(claim.id)}
                  disabled={busyId === claim.id}
                  className={cx(theme.button.primary, theme.button.small, "mt-5")}
                >
                  {busyId === claim.id && <Spinner />}
                  Release to claimant
                </button>
              )}
            </article>
          ))
        )}
      </div>
    </div>
  );
}

/**
 * Entailment is a genuine probability, so unlike the CLIP score it is honest as
 * a percentage. Shown against the threshold rather than alone — the number only
 * means something relative to the line it has to clear.
 */
function Entailment({ score }) {
  if (score === null || score === undefined) {
    return <p className={cx(theme.figure, "mt-4")}>not yet checked</p>;
  }
  const pct = Math.round(score * 100);
  const clears = score >= 0.7;

  return (
    <div className="mt-5">
      <div className="flex items-baseline justify-between gap-3">
        <span className={theme.meta}>matches their record</span>
        <span
          className={cx(
            "font-mono text-sm font-500 tabular-nums",
            clears ? "text-affirm" : "text-alert",
          )}
        >
          {pct}%
        </span>
      </div>

      <div className="relative mt-2.5 h-1.5 rounded-full bg-line">
        <div
          className="h-full rounded-full bg-ink"
          style={{ width: `${Math.max(2, pct)}%` }}
        />
        {/* the 70% line the score has to clear */}
        <span
          className="absolute -top-1 h-3.5 w-0.5 bg-ink"
          style={{ left: "70%" }}
          aria-hidden
        />
      </div>
      <p className={cx(theme.text.tiny, "mt-2")}>
        {clears ? "Above the 70% threshold" : "Below the 70% threshold"}
      </p>
    </div>
  );
}
