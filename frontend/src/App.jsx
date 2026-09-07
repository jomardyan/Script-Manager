import { useCallback, useEffect, useState } from 'react';
import {
  BrowserRouter as Router, Link, NavLink, Navigate, Route, Routes, useLocation,
} from 'react-router-dom';

import Dashboard from './pages/Dashboard';
import Duplicates from './pages/Duplicates';
import FolderRoots from './pages/FolderRoots';
import Login from './pages/Login';
import Monitors from './pages/Monitors';
import Notifications from './pages/Notifications';
import Schedules from './pages/Schedules';
import ScriptDetail from './pages/ScriptDetail';
import Scripts from './pages/Scripts';
import Search from './pages/Search';
import Settings from './pages/Settings';
import SetupWizard from './pages/SetupWizard';
import Tags from './pages/Tags';
import Team from './pages/Team';

import ErrorBoundary from './components/ErrorBoundary';
import ThemeToggle from './components/ThemeToggle';
import { EmptyState, Spinner } from './components/ui';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ToastProvider } from './context/ToastContext';
import { setupApi } from './services/api';

const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '▤', end: true },
  { to: '/folder-roots', label: 'Folder Roots', icon: '▣', permission: 'roots.read' },
  { to: '/scripts', label: 'Scripts', icon: '◈', permission: 'scripts.read' },
  { to: '/duplicates', label: 'Duplicates', icon: '⧉', permission: 'scripts.read' },
  { to: '/tags', label: 'Tags', icon: '◆', permission: 'tags.read' },
  { to: '/search', label: 'Search', icon: '⌕', permission: 'search.read' },
  { to: '/monitors', label: 'Monitors', icon: '♥', permission: 'monitors.read' },
  { to: '/schedules', label: 'Schedules', icon: '⏱', permission: 'schedules.read' },
  { to: '/notifications', label: 'Notifications', icon: '✉', permission: 'notifications.read' },
  { to: '/team', label: 'Team', icon: '☰', adminOnly: true },
  { to: '/settings', label: 'Settings', icon: '⚙' },
];

function Navigation({ onNavigate }) {
  const { can, isAdmin, config } = useAuth();
  const authOff = config?.auth_required === false;

  // Only show what this account can actually reach, so a viewer is not sent to
  // a page that answers 403.
  const visible = NAV_ITEMS.filter((item) => {
    if (item.adminOnly) return authOff || isAdmin;
    if (item.permission) return can(item.permission);
    return true;
  });

  return (
    <nav aria-label="Main">
      <ul>
        {visible.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              end={item.end}
              onClick={onNavigate}
              className={({ isActive }) => (isActive ? 'active' : undefined)}
            >
              <span className="nav-icon" aria-hidden="true">{item.icon}</span>
              {item.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function UserPanel() {
  const { user, signOut, config } = useAuth();

  if (config?.auth_required === false) {
    return (
      <div className="sidebar__footer">
        <p className="text-small text-muted">
          Authentication is disabled on this server (REQUIRE_AUTH=false).
        </p>
        <ThemeToggle />
      </div>
    );
  }

  if (!user) return <div className="sidebar__footer"><ThemeToggle /></div>;

  const roles = (user.roles || []).map((r) => r.name).join(', ');

  return (
    <div className="sidebar__footer">
      <div className="user-chip">
        <span className="user-chip__avatar" aria-hidden="true">
          {(user.full_name || user.username || '?').charAt(0)}
        </span>
        <span className="user-chip__text">
          <span className="user-chip__name" title={user.username}>
            {user.full_name || user.username}
          </span>
          <span className="user-chip__meta" title={roles}>
            {user.is_superuser ? 'Administrator' : (roles || 'No roles')}
          </span>
        </span>
      </div>
      <div className="row row--between">
        <ThemeToggle />
        <button type="button" className="button button-secondary button--small" onClick={signOut}>
          Sign out
        </button>
      </div>
    </div>
  );
}

function NotFound() {
  return (
    <EmptyState
      icon="404"
      title="Page not found"
      description="That URL does not match any page in Script Manager."
      action={<Link className="button" to="/">Back to dashboard</Link>}
    />
  );
}

/** Blocks a route the signed-in account lacks the permission for. */
function RequirePermission({ permission, adminOnly, children }) {
  const { can, isAdmin, config } = useAuth();
  if (config?.auth_required === false) return children;
  if (adminOnly && !isAdmin) {
    return (
      <EmptyState
        icon="⛔"
        title="Administrator access required"
        description="Your account does not have permission to view this page."
        action={<Link className="button button-secondary" to="/">Back to dashboard</Link>}
      />
    );
  }
  if (permission && !can(permission)) {
    return (
      <EmptyState
        icon="⛔"
        title="Not permitted"
        description={`Viewing this page requires the "${permission}" permission.`}
        action={<Link className="button button-secondary" to="/">Back to dashboard</Link>}
      />
    );
  }
  return children;
}

function Shell() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => { setNavOpen(false); }, [location.pathname]);

  useEffect(() => {
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setNavOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, []);

  return (
    <div className="app">
      <a className="skip-link" href="#main">Skip to content</a>

      <header className="topbar">
        <button
          type="button"
          className="button button-secondary button--small"
          onClick={() => setNavOpen((open) => !open)}
          aria-expanded={navOpen}
          aria-controls="app-sidebar"
        >
          <span aria-hidden="true">☰</span> Menu
        </button>
        <span className="sidebar__brand-text">Script Manager</span>
      </header>

      {navOpen && (
        <div
          className="sidebar-scrim"
          onClick={() => setNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside className="sidebar" id="app-sidebar" data-open={navOpen}>
        <div className="sidebar__brand">
          <span className="sidebar__brand-mark" aria-hidden="true">S</span>
          <span className="sidebar__brand-text">Script Manager</span>
        </div>
        <Navigation onNavigate={() => setNavOpen(false)} />
        <UserPanel />
      </aside>

      <main className="main-content" id="main">
        {/* Scoped so a crash in one page keeps the navigation usable. */}
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/folder-roots" element={<RequirePermission permission="roots.read"><FolderRoots /></RequirePermission>} />
            <Route path="/scripts" element={<RequirePermission permission="scripts.read"><Scripts /></RequirePermission>} />
            <Route path="/scripts/:id" element={<RequirePermission permission="scripts.read"><ScriptDetail /></RequirePermission>} />
            <Route path="/duplicates" element={<RequirePermission permission="scripts.read"><Duplicates /></RequirePermission>} />
            <Route path="/tags" element={<RequirePermission permission="tags.read"><Tags /></RequirePermission>} />
            <Route path="/search" element={<RequirePermission permission="search.read"><Search /></RequirePermission>} />
            <Route path="/monitors" element={<RequirePermission permission="monitors.read"><Monitors /></RequirePermission>} />
            <Route path="/schedules" element={<RequirePermission permission="schedules.read"><Schedules /></RequirePermission>} />
            <Route path="/notifications" element={<RequirePermission permission="notifications.read"><Notifications /></RequirePermission>} />
            <Route path="/team" element={<RequirePermission adminOnly><Team /></RequirePermission>} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/login" element={<Navigate to="/" replace />} />
            {/* Catch-all: an unknown URL used to render empty chrome. */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  );
}

function AuthenticatedApp() {
  const { status } = useAuth();

  if (status === 'loading') {
    return <Spinner label="Checking your session" />;
  }
  if (status === 'anonymous') {
    return <Login />;
  }
  return (
    <Router>
      <Shell />
    </Router>
  );
}

/** Distinguishes "setup not done" from "cannot reach the server". */
function SetupGate({ children }) {
  const [state, setState] = useState({ phase: 'loading', error: null });

  const check = useCallback(() => {
    setState({ phase: 'loading', error: null });
    setupApi.getStatus()
      .then((data) => setState({
        phase: data.setup_completed ? 'ready' : 'wizard',
        error: null,
      }))
      // A network failure used to be treated as "setup incomplete", which
      // trapped a fully configured install in the installation wizard.
      .catch((err) => setState({ phase: 'unreachable', error: err.message }));
  }, []);

  useEffect(() => { check(); }, [check]);

  if (state.phase === 'loading') return <Spinner label="Starting Script Manager" />;

  if (state.phase === 'unreachable') {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <h1>Cannot reach the server</h1>
          <p className="auth-card__subtitle">
            Script Manager could not contact its backend API.
          </p>
          <div className="banner banner--error" role="alert">
            <span className="banner__message">{state.error}</span>
          </div>
          <button type="button" className="button button--block" onClick={check}>
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (state.phase === 'wizard') {
    return <SetupWizard onSetupComplete={() => setState({ phase: 'ready', error: null })} />;
  }

  return children;
}

export default function App() {
  return (
    <ErrorBoundary fallbackTitle="Script Manager could not start">
      <ToastProvider>
        <SetupGate>
          <AuthProvider>
            <AuthenticatedApp />
          </AuthProvider>
        </SetupGate>
      </ToastProvider>
    </ErrorBoundary>
  );
}
