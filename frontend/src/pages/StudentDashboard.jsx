// Report something lost, hand something in, review matches, claim.
import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth.jsx";
import ClaimModal from "../components/ClaimModal";
import ItemCard, { Thumbnail } from "../components/ItemCard";
import MatchCard, { relativeConfidence } from "../components/MatchCard";
import { EmptyState, SkeletonList, Spinner } from "../components/Spinner";
import { useToast } from "../components/Toast";
import { cx, labelForStatus, lot, stampFor, theme } from "../theme";

const TABS = [
  {
    id: "lost",
    label: "Report lost",
    heading: "Lost something?",
    lead: "Describe it in your own words. We compare that against photographs of everything handed in.",
  },
  {
    id: "found",
    label: "Hand in",
    heading: "Found something?",
    lead: "Photograph it and take it to the nearest security post. We will find whoever is looking for it.",
  },
  {
    id: "reports",
    label: "My reports",
    heading: "Your reports",
    lead: "Each one stays open and is re-checked against every item handed in.",
  },
  {
    id: "claims",
    label: "My claims",
    heading: "Your claims",
    lead: "Where each of your claims got to.",
  },
];

export default function StudentDashboard() {
  const { user, refresh } = useAuth();
  const toast = useToast();
  const [tab, setTab] = useState("lost");
  const current = TABS.find((t) => t.id === tab);

  return (
    <div>
      <header>
        <span className={theme.meta}>{user?.full_name}</span>
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
        {tab === "lost" && <ReportLost toast={toast} />}
        {tab === "found" && <HandIn toast={toast} onCredit={refresh} />}
        {tab === "reports" && <MyReports toast={toast} />}
        {tab === "claims" && <MyClaims toast={toast} />}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function ReportLost({ toast }) {
  const [form, setForm] = useState({ description: "", location_last_seen: "", private_descriptor: "" });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    try {
      const body = new FormData();
      Object.entries(form).forEach(([k, v]) => body.append(k, v));
      if (file) body.append("image", file);
      const data = await api.reportLost(body);
      setResult(data);
      setForm({ description: "", location_last_seen: "", private_descriptor: "" });
      setFile(null);
      toast.success(
        data.matches.length
          ? `Report filed. ${data.matches.length} possible ${data.matches.length === 1 ? "match" : "matches"} below.`
          : "Report filed. We will check it against everything handed in from now on.",
      );
    } catch (err) {
      toast.error(errorMessage(err, "Could not file the report"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-10">
      <form onSubmit={handleSubmit} className={cx(theme.card, "space-y-6")}>
        <div>
          <label htmlFor="description" className={theme.label}>What did you lose?</label>
          <input
            id="description" required value={form.description} onChange={update("description")}
            placeholder="A black umbrella with a wooden handle" className={theme.input}
          />
          <p className={theme.hint}>Describe the object — colour, material, brand, size.</p>
        </div>

        <div>
          <label htmlFor="location_last_seen" className={theme.label}>Where did you last have it?</label>
          <input
            id="location_last_seen" required value={form.location_last_seen}
            onChange={update("location_last_seen")}
            placeholder="Main library, second floor" className={theme.input}
          />
        </div>

        <div className={theme.rule} />

        <div>
          <label htmlFor="private_descriptor" className={theme.label}>
            A detail only you would know
          </label>
          <textarea
            id="private_descriptor" required rows={3} value={form.private_descriptor}
            onChange={update("private_descriptor")}
            placeholder="A blue sticker under the canopy and a scratch on the handle"
            className={cx(theme.input, "resize-none")}
          />
          <p className={theme.hint}>
            Encrypted, and never shown to anyone. This is what proves the item is yours when you
            claim it.
          </p>
        </div>

        <FilePicker file={file} onPick={setFile} label="Photo, if you have one" />

        <button type="submit" disabled={busy} className={theme.button.primary}>
          {busy && <Spinner />}
          {busy ? "Searching" : "File report and search"}
        </button>
      </form>

      {result && (
        <Matches
          matches={result.matches}
          kind="found"
          lostItemId={result.item.id}
          heading="Possible matches"
          toast={toast}
        />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function HandIn({ toast, onCredit }) {
  const [form, setForm] = useState({ location: "", description: "" });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (!file) return toast.error("Add a photo — the match is made from the picture.");
    setBusy(true);
    try {
      const body = new FormData();
      body.append("image", file);
      body.append("location", form.location);
      if (form.description) body.append("description", form.description);
      const data = await api.submitFound(body);
      setResult(data);
      setForm({ location: "", description: "" });
      setFile(null);
      onCredit?.();
      toast.success("Logged. Take the item to the security post you named.");
    } catch (err) {
      toast.error(errorMessage(err, "Could not log the item"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-10">
      <form onSubmit={handleSubmit} className={cx(theme.card, "space-y-6")}>
        <FilePicker file={file} onPick={setFile} label="Photo of the item" required />

        <div>
          <label htmlFor="location" className={theme.label}>Nearest security post</label>
          <input
            id="location" required value={form.location} onChange={update("location")}
            placeholder="Main Gate Security Post" className={theme.input}
          />
        </div>

        <div>
          <label htmlFor="found_description" className={theme.label}>Description, if you like</label>
          <input
            id="found_description" value={form.description} onChange={update("description")}
            placeholder="Black umbrella, wooden handle" className={theme.input}
          />
          <p className={theme.hint}>Words sharpen the match. The photo alone also works.</p>
        </div>

        <button type="submit" disabled={busy} className={theme.button.primary}>
          {busy && <Spinner />}
          {busy ? "Uploading" : "Log this item"}
        </button>
      </form>

      {result && (
        <section>
          <h2 className={theme.heading.section}>People looking for something like this</h2>
          <div className="mt-4 space-y-3">
            {result.matches.length === 0 ? (
              <div className={theme.cardFlat}>
                <EmptyState
                  title="No open reports match it yet"
                  hint="We will check again each time someone files a report."
                />
              </div>
            ) : (
              result.matches.map((m, i) => (
                <MatchCard
                  key={m.item.id} match={m} kind="lost" rank={i + 1} index={i}
                  confidence={relativeConfidence(result.matches.map((x) => x.score))[i]}
                />
              ))
            )}
          </div>
        </section>
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function MyReports({ toast }) {
  const [reports, setReports] = useState(null);
  const [openId, setOpenId] = useState(null);

  useEffect(() => {
    api.listLost({ mine: true }).then(setReports).catch((err) => {
      toast.error(errorMessage(err, "Could not load your reports"));
      setReports([]);
    });
  }, [toast]);

  if (reports === null) return <SkeletonList />;
  if (reports.length === 0) {
    return (
      <div className={theme.cardFlat}>
        <EmptyState
          title="You have not reported anything lost"
          hint="Use Report lost to describe it — the search runs the moment you file."
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {reports.map((item) => (
        <div key={item.id}>
          <ItemCard
            item={item}
            kind="lost"
            actions={
              <button
                onClick={() => setOpenId(openId === item.id ? null : item.id)}
                className={cx(theme.button.secondary, theme.button.small)}
              >
                {openId === item.id ? "Hide matches" : "See matches"}
              </button>
            }
          />
          {openId === item.id && <LazyMatches lostItemId={item.id} toast={toast} />}
        </div>
      ))}
    </div>
  );
}

function LazyMatches({ lostItemId, toast }) {
  const [matches, setMatches] = useState(null);

  useEffect(() => {
    api.matchesForLost(lostItemId).then(setMatches).catch((err) => {
      toast.error(errorMessage(err, "Could not load matches"));
      setMatches([]);
    });
  }, [lostItemId, toast]);

  return (
    <div className="mt-3 ml-0 space-y-3 border-l border-line pl-4 md:ml-6">
      {matches === null ? (
        <SkeletonList rows={2} />
      ) : (
        <Matches matches={matches} kind="found" lostItemId={lostItemId} toast={toast} />
      )}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function Matches({ matches, kind, lostItemId, heading, toast }) {
  const [active, setActive] = useState(null);
  const [attemptsLeft, setAttemptsLeft] = useState(null);

  const confidences = relativeConfidence(matches.map((m) => m.score));

  const submitClaim = useCallback(
    async (claimant_description) => {
      try {
        const receipt = await api.createClaim({
          lost_item_id: lostItemId,
          found_item_id: active.item.id,
          claimant_description,
        });
        setAttemptsLeft(receipt.attempts_remaining);
        if (receipt.status === "approved") {
          toast.success("Verified. Collect it from the security post.");
          setActive(null);
        } else {
          toast.error(
            `That does not match what you recorded. ${receipt.attempts_remaining} ${receipt.attempts_remaining === 1 ? "attempt" : "attempts"} left.`,
          );
        }
      } catch (err) {
        toast.error(errorMessage(err, "Claim failed"));
        setActive(null);
      }
    },
    [active, lostItemId, toast],
  );

  if (matches.length === 0) {
    return (
      <div className={theme.cardFlat}>
        <EmptyState
          title="Nothing handed in looks like this yet"
          hint="Your report stays open. We check it against every new item."
        />
      </div>
    );
  }

  return (
    <section>
      {heading && (
        <div className="mb-4 flex items-baseline justify-between gap-4">
          <h2 className={theme.heading.section}>{heading}</h2>
          <span className={theme.figure}>{matches.length} of everything handed in</span>
        </div>
      )}
      <div className="space-y-3">
        {matches.map((m, i) => (
          <MatchCard
            key={m.item.id} match={m} kind={kind} rank={i + 1} index={i}
            confidence={confidences[i]} onClaim={() => setActive(m)}
          />
        ))}
      </div>
      <ClaimModal
        open={Boolean(active)}
        match={active}
        attemptsLeft={attemptsLeft}
        onClose={() => setActive(null)}
        onSubmit={submitClaim}
      />
    </section>
  );
}

/* -------------------------------------------------------------------------- */
function MyClaims({ toast }) {
  const [claims, setClaims] = useState(null);

  useEffect(() => {
    api.myClaims().then(setClaims).catch((err) => {
      toast.error(errorMessage(err, "Could not load your claims"));
      setClaims([]);
    });
  }, [toast]);

  if (claims === null) return <SkeletonList rows={2} />;
  if (claims.length === 0) {
    return (
      <div className={theme.cardFlat}>
        <EmptyState
          title="No claims yet"
          hint="When a match looks right, claim it from the match list."
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {claims.map((claim) => {
        const total = claim.attempts_used + claim.attempts_remaining;
        return (
          <div key={claim.id} className={theme.card}>
            <div className="flex items-center justify-between gap-3">
              <span className={theme.meta}>{lot("found", claim.found_item_id)}</span>
              <span className={stampFor(claim.status)}>{labelForStatus(claim.status)}</span>
            </div>

            <p className={cx(theme.text.body, "mt-3")}>
              {claim.status === "approved" && "Verified. Collect it from the security post."}
              {claim.status === "released" && "Returned to you."}
              {claim.status === "rejected" && "The detail did not match your report."}
              {claim.status === "pending" && "Waiting on verification."}
            </p>

            <p className={cx(theme.figure, "mt-2.5")}>
              {claim.attempts_used} of {total} attempts used
            </p>
          </div>
        );
      })}
    </div>
  );
}

/* -------------------------------------------------------------------------- */
function FilePicker({ file, onPick, label, required }) {
  const [preview, setPreview] = useState(null);

  const handle = (event) => {
    const picked = event.target.files?.[0] ?? null;
    onPick(picked);
    setPreview(picked ? URL.createObjectURL(picked) : null);
  };

  useEffect(() => {
    if (!file) setPreview(null);
  }, [file]);

  return (
    <div>
      <span className={theme.label}>{label}</span>
      <div className="flex items-center gap-4">
        {preview ? (
          <Thumbnail src={preview} alt="Selected" className="h-20 w-20" />
        ) : (
          <div className="grid h-20 w-20 shrink-0 place-items-center rounded-md bg-ground">
            <span className="u-meta text-mist">empty</span>
          </div>
        )}
        <div className="min-w-0">
          <label className={cx(theme.button.secondary, theme.button.small, "cursor-pointer")}>
            {file ? "Change photo" : "Choose photo"}
            <input
              type="file" accept="image/jpeg,image/png,image/webp"
              onChange={handle} required={required && !file} className="sr-only"
            />
          </label>
          {file && <p className={cx(theme.figure, "mt-2 truncate")}>{file.name}</p>}
        </div>
      </div>
    </div>
  );
}
