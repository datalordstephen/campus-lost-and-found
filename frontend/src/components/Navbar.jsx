// The rail: solid ink against the white field, carrying the wordmark, the
// role's routes, and who you are signed in as.
import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { cx, theme } from "../theme";
import { useAuth } from "../auth.jsx";

const ROUTES = {
  student: [{ to: "/student", label: "My items" }],
  security: [{ to: "/security", label: "Property desk" }],
  admin: [
    { to: "/admin", label: "Administration" },
    { to: "/security", label: "Property desk" },
    { to: "/student", label: "Student view" },
  ],
};

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);

  const routes = ROUTES[user?.role] ?? [];
  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <>
      {/* Mobile: the rail collapses to a bar and slides back in. */}
      <header className="sticky top-0 z-40 flex items-center justify-between bg-ink px-5 py-3.5 md:hidden">
        <Wordmark />
        <button onClick={() => setOpen(true)} className="u-meta text-mist hover:text-paper">
          menu
        </button>
      </header>

      {open && (
        <div className="fixed inset-0 z-50 flex md:hidden">
          <nav className={cx(theme.layout.rail, "flex w-60 flex-col")}>
            <RailBody
              routes={routes}
              user={user}
              onLogout={handleLogout}
              onNavigate={() => setOpen(false)}
              onClose={() => setOpen(false)}
            />
          </nav>
          <button
            className="flex-1 bg-ink/40 backdrop-blur-[2px]"
            onClick={() => setOpen(false)}
            aria-label="Close menu"
          />
        </div>
      )}

      <nav className={cx(theme.layout.rail, "hidden md:block")}>
        <div className={theme.layout.railInner}>
          <RailBody routes={routes} user={user} onLogout={handleLogout} />
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

function RailBody({ routes, user, onLogout, onNavigate, onClose }) {
  return (
    <>
      <div className="flex items-start justify-between px-5 pt-6 pb-8">
        <div>
          <Wordmark />
          <p className="u-meta mt-2 text-white/55">Campus property</p>
        </div>
        {onClose && (
          <button onClick={onClose} className="u-meta text-mist md:hidden">
            close
          </button>
        )}
      </div>

      <div className="flex-1 space-y-0.5 px-3">
        {routes.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            onClick={onNavigate}
            className={({ isActive }) => (isActive ? theme.nav.linkActive : theme.nav.link)}
          >
            {label}
          </NavLink>
        ))}
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

        <button
          onClick={onLogout}
          className="u-meta mt-4 text-mist transition-colors duration-150 hover:text-paper"
        >
          Sign out
        </button>
      </div>
    </>
  );
}
