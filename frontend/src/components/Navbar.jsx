// The rail: solid ink against the white field. It carries the wordmark, the
// sections of the current workspace, a way to cross to another workspace when
// the account has more than one, and who you are signed in as.
import { useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { SECTIONS } from "../sections";
import { cx, theme } from "../theme";
import { useAuth } from "../auth.jsx";

// Which workspaces a role may enter. Students have one, so they never see a
// switcher; admins can look at all three.
const WORKSPACES = {
  student: [["student", "My items"]],
  security: [["security", "Property desk"]],
  admin: [
    ["admin", "Administration"],
    ["security", "Property desk"],
    ["student", "Student view"],
  ],
};

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <>
      <header className="sticky top-0 z-40 flex items-center justify-between bg-ink px-5 py-3.5 md:hidden">
        <Wordmark />
        <button onClick={() => setOpen(true)} className="u-meta text-mist hover:text-paper">
          menu
        </button>
      </header>

      {open && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <nav className={cx(theme.layout.rail, "flex w-60 flex-col")}>
            <RailBody user={user} onLogout={handleLogout} onNavigate={() => setOpen(false)}
                      onClose={() => setOpen(false)} />
          </nav>
          <button className="flex-1 bg-ink/40 backdrop-blur-[2px]" onClick={() => setOpen(false)}
                  aria-label="Close menu" />
        </div>
      )}

      <nav className={cx(theme.layout.rail, "hidden md:block")}>
        <div className={theme.layout.railInner}>
          <RailBody user={user} onLogout={handleLogout} />
        </div>
      </nav>
    </>
  );
}

function Wordmark() {
  return (
    <span className="u-display text-[1.0625rem] leading-none text-paper">
      Lost&nbsp;&amp;&nbsp;Found
    </span>
  );
}

function RailBody({ user, onLogout, onNavigate, onClose }) {
  const { pathname } = useLocation();
  const workspaces = WORKSPACES[user?.role] ?? [];
  const current = workspaces.find(([id]) => pathname.startsWith(`/${id}`))?.[0]
    ?? workspaces[0]?.[0];
  const sections = SECTIONS[current] ?? [];

  return (
    <>
      <div className="flex items-start justify-between px-5 pt-6 pb-7">
        <div>
          <Wordmark />
          <p className="u-meta mt-2 text-white/55">Campus property</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="u-meta text-mist md:hidden">close</button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        <div className="space-y-0.5">
          {sections.map(({ id, label }) => (
            <NavLink
              key={id}
              to={`/${current}/${id}`}
              onClick={onNavigate}
              className={({ isActive }) => (isActive ? theme.nav.linkActive : theme.nav.link)}
            >
              {label}
            </NavLink>
          ))}
        </div>

        {/* Only shown to an account that can actually be in more than one place. */}
        {workspaces.length > 1 && (
          <div className="mt-6 border-t border-white/10 pt-4">
            <p className="u-meta px-3 pb-2 text-white/40">Switch to</p>
            <div className="space-y-0.5">
              {workspaces
                .filter(([id]) => id !== current)
                .map(([id, label]) => (
                  <NavLink key={id} to={`/${id}`} onClick={onNavigate} className={theme.nav.link}>
                    {label}
                  </NavLink>
                ))}
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-white/10 p-5">
        <p className="truncate text-sm font-500 text-paper">{user?.full_name}</p>
        <p className="u-meta mt-1.5 text-white/55">{user?.role}</p>

        {user?.role === "student" && (
          <p className="mt-3 font-mono text-xs tabular-nums text-white/50">
            {user?.incentive_credits ?? 0} return credit
            {user?.incentive_credits === 1 ? "" : "s"}
          </p>
        )}

        <button onClick={onLogout}
                className="u-meta mt-4 text-mist transition-colors duration-150 hover:text-paper">
          Sign out
        </button>
      </div>
    </>
  );
}
