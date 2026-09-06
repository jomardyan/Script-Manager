import { useEffect, useState } from 'react';
import { apiError, authApi } from '../services/api';
import { useAuth } from '../context/AuthContext';
import { Field } from '../components/ui';
import ThemeToggle from '../components/ThemeToggle';

/**
 * Sign-in screen.
 *
 * The application previously had no login at all: the API client never sent a
 * token, so every authenticated endpoint (team management, running a job,
 * testing a notification channel) was permanently out of reach from the UI.
 */
export default function Login() {
  const { signIn, config } = useAuth();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [noUsers, setNoUsers] = useState(false);

  useEffect(() => {
    document.title = 'Sign in · Script Manager';
  }, []);

  useEffect(() => {
    // Tell an operator why nobody can sign in rather than only rejecting them.
    let cancelled = false;
    authApi.config()
      .then(({ data }) => { if (!cancelled) setNoUsers(data?.has_users === false); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    if (busy) return;
    setError(null);
    setBusy(true);
    try {
      await signIn(username.trim(), password);
    } catch (err) {
      setError(apiError(err));
      setBusy(false);
    }
  };

  return (
    <div className="auth-screen">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="sidebar__brand-mark" aria-hidden="true">S</span>
          <span className="sidebar__brand-text">Script Manager</span>
        </div>
        <h1>Sign in</h1>
        <p className="auth-card__subtitle">Use your Script Manager account to continue.</p>

        {noUsers && (
          <div className="banner banner--warning" role="status">
            <span className="banner__message">
              This installation has no user accounts yet. Check the backend logs for the
              bootstrap administrator password, or re-run the setup wizard.
            </span>
          </div>
        )}

        {error && (
          <div className="banner banner--error" role="alert">
            <span className="banner__message">{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <Field label="Username" required>
            {(props) => (
              <input
                {...props}
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            )}
          </Field>

          <Field label="Password" required>
            {(props) => (
              <input
                {...props}
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            )}
          </Field>

          <button type="submit" className="button button--block" disabled={busy}>
            {busy ? (
              <>
                <span className="spinner spinner--inline" aria-hidden="true" />
                Signing in…
              </>
            ) : 'Sign in'}
          </button>
        </form>

        {config?.self_registration_enabled && (
          <p className="text-small text-muted" style={{ marginTop: 'var(--space-4)', textAlign: 'center' }}>
            Self-registration is enabled on this server. Ask an administrator for an
            account, or register through the API.
          </p>
        )}

        <div className="row row--end" style={{ marginTop: 'var(--space-4)' }}>
          <ThemeToggle />
        </div>
      </div>
    </div>
  );
}
