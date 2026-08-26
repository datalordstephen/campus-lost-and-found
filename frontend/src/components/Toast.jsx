// Minimal toast system — no library, per SPEC.md.
import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { cx, theme } from "../theme";

const ToastContext = createContext(null);

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);

  const dismiss = useCallback(
    (id) => setToasts((current) => current.filter((t) => t.id !== id)),
    [],
  );

  const push = useCallback(
    (message, variant, ttl) => {
      const id = crypto.randomUUID();
      setToasts((current) => [...current, { id, message, variant }]);
      setTimeout(() => dismiss(id), ttl);
    },
    [dismiss],
  );

  const value = useMemo(
    () => ({
      success: (m) => push(m, "success", 4000),
      error: (m) => push(m, "error", 6000),
      info: (m) => push(m, "info", 4000),
    }),
    [push],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className={theme.toast.wrap} role="status" aria-live="polite">
        {toasts.map(({ id, message, variant }) => (
          <div key={id} className={cx(theme.toast.base, "rise")}>
            {/* The one functional mark: a dot, not a coloured panel. */}
            <span
              aria-hidden
              className={cx(
                "mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full",
                variant === "error" && "bg-alert",
                variant === "success" && "bg-affirm",
                variant === "info" && "bg-mist",
              )}
            />
            <span className="flex-1 leading-relaxed">{message}</span>
            <button
              onClick={() => dismiss(id)}
              className="u-meta shrink-0 pt-1 text-mist transition-colors duration-150 hover:text-paper"
            >
              close
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export const useToast = () => useContext(ToastContext);
