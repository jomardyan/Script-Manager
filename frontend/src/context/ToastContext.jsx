import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';

const ToastContext = createContext(null);

const DEFAULT_DURATION = 5000;
const ERROR_DURATION = 8000;

/**
 * Non-blocking notifications.
 *
 * Replaces `alert()`, which froze the page, could not be styled, showed one
 * message at a time and was invisible to assistive technology. The stack is an
 * aria-live region so screen readers announce results too.
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const timers = useRef(new Map());
  const nextId = useRef(1);

  const dismiss = useCallback((id) => {
    setToasts((current) => current.filter((t) => t.id !== id));
    const timer = timers.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timers.current.delete(id);
    }
  }, []);

  const push = useCallback((message, { type = 'info', duration } = {}) => {
    const id = nextId.current;
    nextId.current += 1;
    const text = typeof message === 'string' ? message : String(message?.message || message);
    setToasts((current) => [...current, { id, type, message: text }]);

    const ms = duration ?? (type === 'error' ? ERROR_DURATION : DEFAULT_DURATION);
    if (ms > 0) {
      timers.current.set(id, setTimeout(() => dismiss(id), ms));
    }
    return id;
  }, [dismiss]);

  // Clear pending timers on unmount so nothing fires against a dead tree.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      pending.forEach((timer) => clearTimeout(timer));
      pending.clear();
    };
  }, []);

  const value = useMemo(() => ({
    push,
    dismiss,
    success: (message, options) => push(message, { ...options, type: 'success' }),
    error: (message, options) => push(message, { ...options, type: 'error' }),
    info: (message, options) => push(message, { ...options, type: 'info' }),
    warning: (message, options) => push(message, { ...options, type: 'warning' }),
  }), [push, dismiss]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack">
        {/* Polite for routine results, assertive for failures. */}
        <div aria-live="polite" aria-atomic="false" className="toast-region">
          {toasts.filter((t) => t.type !== 'error').map((toast) => (
            <Toast key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
        <div role="alert" aria-live="assertive" className="toast-region">
          {toasts.filter((t) => t.type === 'error').map((toast) => (
            <Toast key={toast.id} toast={toast} onDismiss={dismiss} />
          ))}
        </div>
      </div>
    </ToastContext.Provider>
  );
}

const ICONS = { success: '✓', error: '!', warning: '!', info: 'i' };

function Toast({ toast, onDismiss }) {
  return (
    <div className={`toast toast--${toast.type}`}>
      <span className="toast__icon" aria-hidden="true">{ICONS[toast.type] || 'i'}</span>
      <span className="toast__message">{toast.message}</span>
      <button
        type="button"
        className="toast__close"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error('useToast must be used inside a ToastProvider');
  return context;
}
