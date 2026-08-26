import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { HOME_FOR_ROLE, useAuth } from "../auth.jsx";
import { Spinner } from "../components/Spinner";
import AuthLayout from "../components/AuthLayout";
import { cx, theme } from "../theme";

export default function Login() {
  const { user, adopt } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={HOME_FOR_ROLE[user.role] ?? "/student"} replace />;

  const handleSubmit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const me = adopt(await api.login(form));
      navigate(HOME_FOR_ROLE[me.role] ?? "/student", { replace: true });
    } catch (err) {
      setError(errorMessage(err, "Could not sign in"));
    } finally {
      setBusy(false);
    }
  };

  const update = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  return (
    <AuthLayout>
      <div>
        <h2 className={theme.display.md}>Sign in</h2>
        <p className={cx(theme.text.muted, "mt-2")}>Use your campus email address.</p>

        <form onSubmit={handleSubmit} className="mt-8 space-y-5">
          <div>
            <label htmlFor="email" className={theme.label}>
              Email
            </label>
            <input
              id="email" type="email" required autoComplete="email"
              value={form.email} onChange={update("email")}
              placeholder="you@campus.edu" className={theme.input}
            />
          </div>
          <div>
            <label htmlFor="password" className={theme.label}>
              Password
            </label>
            <input
              id="password" type="password" required autoComplete="current-password"
              value={form.password} onChange={update("password")}
              placeholder="Your password" className={theme.input}
            />
          </div>

          {error && <p className={theme.error}>{error}</p>}

          <button type="submit" disabled={busy} className={cx(theme.button.primary, "w-full")}>
            {busy && <Spinner />}
            {busy ? "Signing in" : "Sign in"}
          </button>
        </form>

        <p className={cx(theme.text.muted, "mt-8")}>
          No account?{" "}
          <Link to="/register" className="font-500 text-ink underline underline-offset-4">
            Register
          </Link>
        </p>
      </div>
    </AuthLayout>
  );
}
