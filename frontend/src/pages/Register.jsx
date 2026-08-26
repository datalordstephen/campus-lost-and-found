import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { HOME_FOR_ROLE, useAuth } from "../auth.jsx";
import { Spinner } from "../components/Spinner";
import AuthLayout from "../components/AuthLayout";
import { cx, theme } from "../theme";

const ROLES = [
  { value: "student", label: "Student" },
  { value: "security", label: "Security officer" },
  { value: "admin", label: "Administrator" },
];

export default function Register() {
  const { user, adopt } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ full_name: "", email: "", password: "", role: "student" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={HOME_FOR_ROLE[user.role] ?? "/student"} replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (form.password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const me = adopt(await api.register(form));
      navigate(HOME_FOR_ROLE[me.role] ?? "/student", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not create the account"));
    } finally {
      setBusy(false);
    }
  };

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <AuthLayout>
      <div>
        <h2 className={theme.display.md}>Create an account</h2>
        <p className={cx(theme.text.muted, "mt-2")}>Takes about ten seconds.</p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="full_name" className={theme.label}>Full name</label>
            <input
              id="full_name" required autoComplete="name"
              value={form.full_name} onChange={update("full_name")}
              placeholder="Ada Lovelace" className={theme.input}
            />
          </div>
          <div>
            <label htmlFor="email" className={theme.label}>Email</label>
            <input
              id="email" type="email" required autoComplete="email"
              value={form.email} onChange={update("email")}
              placeholder="you@campus.edu" className={theme.input}
            />
          </div>
          <div>
            <label htmlFor="password" className={theme.label}>Password</label>
            <input
              id="password" type="password" required minLength={8} autoComplete="new-password"
              value={form.password} onChange={update("password")}
              placeholder="At least 8 characters" className={theme.input}
            />
          </div>
          <div>
            <label htmlFor="role" className={theme.label}>Role</label>
            <select id="role" value={form.role} onChange={update("role")} className={theme.input}>
              {ROLES.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <p className={theme.hint}>
              Staff roles are open to pick in this build. A live deployment would issue them.
            </p>
          </div>

          {error && <p className={theme.error}>{error}</p>}

          <button type="submit" disabled={busy} className={cx(theme.button.primary, "w-full")}>
            {busy && <Spinner />}
            {busy ? "Creating account" : "Create account"}
          </button>
        </form>

        <p className={cx(theme.text.muted, "mt-8")}>
          Already registered?{" "}
          <Link to="/login" className="font-500 text-ink underline underline-offset-4">
            Sign in
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
