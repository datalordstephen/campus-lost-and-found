// Accounts, listings, and how the system is doing.
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth.jsx";
import ItemCard from "../components/ItemCard";
import { EmptyState, SkeletonList, Spinner } from "../components/Spinner";
import { useToast } from "../components/Toast";
import { cx, theme } from "../theme";

const TABS = [
  { id: "stats", label: "Overview" },
  { id: "users", label: "People" },
  { id: "listings", label: "Listings" },
];

export default function AdminPanel() {
  const toast = useToast();
  const [tab, setTab] = useState("stats");

  return (
    <div>
      <header>
        <span className={theme.meta}>Administration</span>
        <h1 className={cx(theme.heading.page, "mt-3")}>How it&rsquo;s going</h1>
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
        {tab === "stats" && <Overview toast={toast} />}
        {tab === "users" && <People toast={toast} />}
        {tab === "listings" && <Listings toast={toast} />}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function Overview({ toast }) {
  const [stats, setStats] = useState(null);
  const [rebuilding, setRebuilding] = useState(false);

  const load = useCallback(() => {
    api.adminStats().then(setStats).catch((err) => {
      toast.error(errorMessage(err, "Could not load the overview"));
      setStats(false);
    });
  }, [toast]);

  useEffect(load, [load]);

  const rebuild = async () => {
    setRebuilding(true);
    try {
      const { detail } = await api.adminRebuildIndex();
      toast.success(detail);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Rebuild failed"));
    } finally {
      setRebuilding(false);
    }
  };

  if (stats === null) return <SkeletonList rows={2} />;
  if (stats === false) return null;

  // The headline number is the only one that matters: things actually returned.
  const returnRate =
    stats.total_claims > 0 ? Math.round((stats.claims_released / stats.total_claims) * 100) : null;

  const figures = [
    ["Handed in", stats.total_found_items],
    ["Reported lost", stats.total_lost_items],
    ["Claims made", stats.total_claims],
    ["People", stats.total_users],
    ["Items indexed", stats.faiss_vectors],
  ];

  return (
    <div className="space-y-10">
      <section className={cx(theme.card, "sm:p-8")}>
        <span className={theme.meta}>Returned to their owner</span>
        <p className="u-display mt-3 text-[clamp(3.5rem,12vw,6rem)] tabular-nums">
          {stats.claims_released}
        </p>
        <p className={cx(theme.text.muted, "mt-1")}>
          {returnRate === null
            ? "No claims have been made yet."
            : `${returnRate}% of every claim made so far.`}
        </p>
      </section>

      <section>
        <h2 className={theme.heading.section}>Everything else</h2>
        <dl className="mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-lg bg-line sm:grid-cols-3">
          {figures.map(([label, value]) => (
            <div key={label} className="bg-paper p-5">
              <dt className={theme.meta}>{label}</dt>
              <dd className="u-display mt-2.5 text-3xl tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <h2 className={theme.heading.section}>Accounts by role</h2>
        <div className={cx(theme.card, "mt-4 space-y-3")}>
          {Object.keys(stats.users_by_role).length === 0 ? (
            <EmptyState title="Nobody has registered yet" />
          ) : (
            Object.entries(stats.users_by_role).map(([role, count]) => (
              <div key={role} className="flex items-baseline justify-between gap-4">
                <span className={theme.meta}>{role}</span>
                <span className="font-mono text-sm tabular-nums text-ink">{count}</span>
              </div>
            ))
          )}
        </div>
      </section>

      <section className={cx(theme.card, "flex flex-wrap items-center justify-between gap-4")}>
        <div className="min-w-0">
          <h2 className={theme.heading.section}>Compact the search index</h2>
          <p className={cx(theme.text.muted, "mt-1.5 max-w-sm")}>
            Clears out removed items and renumbers the rest. Safe to run any time.
          </p>
        </div>
        <button onClick={rebuild} disabled={rebuilding} className={theme.button.secondary}>
          {rebuilding && <Spinner />}
          {rebuilding ? "Rebuilding" : "Rebuild"}
        </button>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function People({ toast }) {
  const { user: me } = useAuth();
  const [users, setUsers] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    api.adminUsers().then(setUsers).catch((err) => {
      toast.error(errorMessage(err, "Could not load people"));
      setUsers([]);
    });
  }, [toast]);

  useEffect(load, [load]);

  const setRole = async (id, role) => {
    setBusyId(id);
    try {
      await api.adminSetRole(id, role);
      toast.success("Role updated.");
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Could not change the role"));
    } finally {
      setBusyId(null);
    }
  };

  if (users === null) return <SkeletonList rows={3} />;
  if (users.length === 0) {
    return (
      <div className={theme.cardFlat}>
        <EmptyState title="Nobody has registered yet" />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {users.map((user) => (
        <div key={user.id} className={cx(theme.card, "flex flex-wrap items-center gap-4")}>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-500 text-ink">{user.full_name}</p>
            <p className={cx(theme.figure, "mt-1 truncate")}>{user.email}</p>
          </div>

          {user.incentive_credits > 0 && (
            <span className={theme.figure}>{user.incentive_credits} credits</span>
          )}

          <select
            value={user.role}
            disabled={busyId === user.id || user.id === me?.id}
            onChange={(e) => setRole(user.id, e.target.value)}
            className={cx(theme.input, "w-auto py-1.5 text-xs disabled:opacity-40")}
            title={user.id === me?.id ? "You cannot change your own role" : undefined}
          >
            <option value="student">student</option>
            <option value="security">security</option>
            <option value="admin">admin</option>
          </select>
        </div>
      ))}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function Listings({ toast }) {
  const [kind, setKind] = useState("found");
  const [items, setItems] = useState(null);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(() => {
    setItems(null);
    (kind === "found" ? api.listFound() : api.listLost())
      .then(setItems)
      .catch((err) => {
        toast.error(errorMessage(err, "Could not load listings"));
        setItems([]);
      });
  }, [kind, toast]);

  useEffect(load, [load]);

  const remove = async (id) => {
    if (!window.confirm(`Remove ${kind} item #${id} for good? This cannot be undone.`)) return;
    setBusyId(id);
    try {
      const { detail } =
        kind === "found" ? await api.adminDeleteFound(id) : await api.adminDeleteLost(id);
      toast.success(detail);
      load();
    } catch (err) {
      toast.error(errorMessage(err, "Could not remove the listing"));
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div>
      <div className="flex gap-1.5">
        {["found", "lost"].map((value) => (
          <button
            key={value}
            onClick={() => setKind(value)}
            className={cx(theme.chip.base, kind === value ? theme.chip.on : theme.chip.off)}
          >
            {value === "found" ? "Handed in" : "Reported lost"}
          </button>
        ))}
      </div>

      <div className="mt-5 space-y-3">
        {items === null ? (
          <SkeletonList />
        ) : items.length === 0 ? (
          <div className={theme.cardFlat}>
            <EmptyState title={kind === "found" ? "Nothing handed in" : "Nothing reported lost"} />
          </div>
        ) : (
          items.map((item) => (
            <ItemCard
              key={item.id}
              item={item}
              kind={kind}
              actions={
                <button
                  onClick={() => remove(item.id)}
                  disabled={busyId === item.id}
                  className={cx(theme.button.danger, theme.button.small)}
                >
                  {busyId === item.id && <Spinner />}
                  Remove listing
                </button>
              }
            />
          ))
        )}
      </div>
    </div>
  );
}
