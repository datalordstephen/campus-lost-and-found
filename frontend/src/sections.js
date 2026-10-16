// The sections of each role's workspace, in one place so the sidebar, the
// mobile section row and the page headings can never disagree.
//
// Each is a real route (/student/hand-in, /security/claims, ...) so the sidebar
// navigates, the back button works, and a section can be linked to directly.

export const SECTIONS = {
  student: [
    {
      id: "report-lost",
      label: "Report lost",
      heading: "Lost something?",
      lead: "Describe it in your own words. We compare that against photographs of everything handed in.",
    },
    {
      id: "hand-in",
      label: "Hand in",
      heading: "Found something?",
      lead: "Photograph it and take it to the nearest security post. We will find whoever is looking for it.",
    },
    {
      id: "handed-in",
      label: "Handed in",
      heading: "What you handed in",
      lead: "Everything you turned in, and whether it made it back to its owner.",
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
  ],
  security: [
    {
      id: "incoming",
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
  ],
  admin: [
    { id: "overview", label: "Overview", heading: "How it’s going", lead: "" },
    {
      id: "people",
      label: "People",
      heading: "People",
      lead: "Accounts and what each one can do.",
    },
    {
      id: "listings",
      label: "Listings",
      heading: "Listings",
      lead: "Remove stale entries. This deletes the item, its photo and its vector.",
    },
  ],
};

/** The section named in the URL, or the first one if the URL names nothing valid. */
export function resolveSection(workspace, id) {
  const sections = SECTIONS[workspace] ?? [];
  return sections.find((s) => s.id === id) ?? sections[0];
}
