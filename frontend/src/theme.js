// Design system. Every component imports from here — never hardcode class strings.
//
// Direction: ink on paper. The interface is achromatic so that the photographs
// of lost objects are the only colour in the product. Structure comes from
// weight, scale and white space rather than from rules and boxes — hairlines
// are used only where they carry meaning.
//
// Type does three jobs and no more:
//   display  Archivo 800, tracked tight — headlines and numbers that matter
//   body     Archivo 400/500 — everything a person reads as prose
//   meta     JetBrains Mono, uppercase, wide — lot numbers, scores, timestamps,
//            status stamps. The ledger voice. Never used for prose.

export const theme = {
  // ---- surfaces ----------------------------------------------------------
  // No border. Cards separate from the field by tone and a soft lift, which
  // keeps the page from reading as a ruled form.
  card: "rounded-lg bg-paper p-5 shadow-[0_1px_2px_rgba(10,10,10,0.04),0_8px_24px_-12px_rgba(10,10,10,0.10)]",
  cardFlat: "rounded-lg bg-paper p-5",
  cardInset: "rounded-lg bg-ground p-4",
  well: "rounded-lg border border-line bg-ground/60 p-4",

  // ---- type --------------------------------------------------------------
  display: {
    xl: "u-display text-[clamp(2.5rem,7vw,4rem)]",
    lg: "u-display text-[clamp(2rem,5vw,2.75rem)]",
    md: "u-display text-2xl",
  },
  heading: {
    page: "u-display text-[clamp(2rem,5vw,2.75rem)]",
    section: "text-base font-600 tracking-[-0.01em] text-ink",
    card: "text-[0.9375rem] font-500 leading-snug text-ink",
  },
  text: {
    lead: "text-base leading-relaxed text-ash",
    body: "text-sm leading-relaxed text-ink",
    muted: "text-sm leading-relaxed text-ash",
    tiny: "text-xs leading-relaxed text-mist",
  },
  // The ledger voice.
  meta: "u-meta text-ash",
  metaInk: "u-meta text-ink",
  // Lot numbers and measured quantities: mono, not uppercase, tabular.
  figure: "font-mono text-xs tabular-nums text-ash",
  figureInk: "font-mono text-sm tabular-nums text-ink",

  // ---- controls ----------------------------------------------------------
  button: {
    primary:
      "inline-flex items-center justify-center gap-2 rounded-md bg-ink px-4 py-2.5 text-sm font-500 text-paper transition-colors duration-150 hover:bg-graphite disabled:opacity-40 disabled:pointer-events-none",
    secondary:
      "inline-flex items-center justify-center gap-2 rounded-md border border-line bg-paper px-4 py-2.5 text-sm font-500 text-ink transition-colors duration-150 hover:border-ink disabled:opacity-40 disabled:pointer-events-none",
    ghost:
      "inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-500 text-ash transition-colors duration-150 hover:bg-ground hover:text-ink disabled:opacity-40 disabled:pointer-events-none",
    danger:
      "inline-flex items-center justify-center gap-2 rounded-md border border-alert/30 bg-paper px-4 py-2.5 text-sm font-500 text-alert transition-colors duration-150 hover:bg-alert hover:text-paper hover:border-alert disabled:opacity-40 disabled:pointer-events-none",
    small: "px-3 py-1.5 text-[0.8125rem]",
  },

  label: "u-meta mb-2 block font-700 text-ink",
  input:
    "w-full rounded-md border border-line bg-paper px-3.5 py-2.5 text-sm text-ink placeholder-mist transition-colors duration-150 focus:border-ink focus:outline-none",
  hint: "mt-2 text-xs leading-relaxed text-mist",
  error: "text-sm text-alert",

  // ---- status stamps -----------------------------------------------------
  // Marked, not badged. A stamp is square-cornered mono in a hairline box —
  // the marking an actual property office puts on a tag.
  stamp: {
    base: "u-meta inline-flex items-center gap-1.5 border px-2 py-1",
    open: "border-ink/25 text-ink",
    wait: "border-line bg-ground text-ash",
    done: "border-transparent bg-ink text-paper",
    good: "border-affirm/30 text-affirm",
    bad: "border-alert/30 text-alert",
  },

  // ---- shell -------------------------------------------------------------
  layout: {
    shell: "min-h-screen bg-ground md:flex",
    // The column carries the ink so it paints to the bottom of a long page;
    // the inner panel is what actually sticks to the viewport.
    rail: "w-52 shrink-0 bg-ink",
    railInner: "flex h-screen flex-col md:sticky md:top-0",
    main: "min-w-0 flex-1",
    content: "mx-auto max-w-4xl px-5 py-10 md:px-10 md:py-14",
  },
  nav: {
    link: "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-500 text-mist transition-colors duration-150 hover:bg-white/8 hover:text-paper",
    linkActive: "flex items-center gap-3 rounded-md bg-white/12 px-3 py-2 text-sm font-500 text-paper",
  },

  // Auth is a split: ink on the left carrying the promise, paper on the right
  // carrying the form. It uses the whole viewport instead of stranding a narrow
  // column in the middle of it.
  auth: {
    shell: "min-h-screen lg:grid lg:grid-cols-[1.1fr_1fr]",
    aside: "relative hidden flex-col justify-between bg-ink p-12 lg:flex",
    pane: "flex min-h-screen items-center justify-center bg-ground px-5 py-12 lg:min-h-0",
    card: "w-full max-w-[24rem]",
  },

  modal: {
    backdrop:
      "fixed inset-0 z-50 flex items-end justify-center bg-ink/40 p-0 backdrop-blur-[2px] sm:items-center sm:p-6",
    panel:
      "max-h-[92vh] w-full overflow-y-auto rounded-t-xl bg-paper p-6 shadow-2xl sm:max-w-md sm:rounded-xl",
  },

  toast: {
    wrap: "fixed bottom-4 left-4 right-4 z-60 flex flex-col gap-2 sm:left-auto sm:w-[22rem]",
    base: "flex items-start gap-3 rounded-lg bg-ink px-4 py-3 text-sm text-paper shadow-lg",
  },

  // Tabs read as a row of labels with the active one underscored in ink.
  tab: {
    row: "flex gap-6 overflow-x-auto border-b border-line",
    item: "u-meta -mb-px shrink-0 border-b-2 border-transparent py-3 text-ash transition-colors duration-150 hover:text-ink",
    itemActive: "u-meta -mb-px shrink-0 border-b-2 border-ink py-3 font-700 text-ink",
  },

  chip: {
    base: "u-meta rounded-full px-3 py-1.5 transition-colors duration-150",
    on: "bg-ink text-paper",
    off: "text-ash hover:bg-line/60 hover:text-ink",
  },

  skeleton: "animate-pulse rounded-md bg-line/70",
  rule: "border-t border-line",
  empty: "px-4 py-14 text-center",
};

// A status becomes a stamp. Grouped by what the status means to the reader,
// not by which table it came from.
const STAMP = {
  open: theme.stamp.open,
  verified: theme.stamp.open,
  approved: theme.stamp.good,
  pending: theme.stamp.wait,
  pending_custody: theme.stamp.wait,
  matched: theme.stamp.wait,
  claimed: theme.stamp.done,
  released: theme.stamp.done,
  rejected: theme.stamp.bad,
};

export const stampFor = (status) => `${theme.stamp.base} ${STAMP[status] ?? theme.stamp.wait}`;

export const labelForStatus = (status) => String(status ?? "").replace(/_/g, " ");

// Lot numbers. A found item is lot F-014; a report is R-007. Reading an id as
// a lot is the whole conceit of the interface, so it lives here.
export const lot = (kind, id) =>
  `${kind === "found" ? "F" : "R"}-${String(id).padStart(3, "0")}`;

export const cx = (...parts) => parts.filter(Boolean).join(" ");
