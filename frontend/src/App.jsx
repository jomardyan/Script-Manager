import { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import FolderRoots from './pages/FolderRoots';
import Scripts from './pages/Scripts';
import ScriptDetail from './pages/ScriptDetail';
import Tags from './pages/Tags';
import Search from './pages/Search';
import SetupWizard from './pages/SetupWizard';
import Monitors from './pages/Monitors';
import Schedules from './pages/Schedules';
import Notifications from './pages/Notifications';
import Team from './pages/Team';
import { setupApi } from './services/api';

function Navigation() {
  const location = useLocation();
  
  const isActive = (path) => {
    return location.pathname === path ? 'active' : '';
  };
  
  return (
    <nav>
      <ul>
        <li>
          <Link to="/" className={isActive('/')}>Dashboard</Link>
        </li>
        <li>
          <Link to="/folder-roots" className={isActive('/folder-roots')}>Folder Roots</Link>
        </li>
        <li>
          <Link to="/scripts" className={isActive('/scripts')}>Scripts</Link>
        </li>
        <li>
          <Link to="/tags" className={isActive('/tags')}>Tags</Link>
        </li>
        <li>
          <Link to="/search" className={isActive('/search')}>Search</Link>
        </li>
        <li>
          <Link to="/monitors" className={isActive('/monitors')}>Monitors</Link>
        </li>
        <li>
          <Link to="/schedules" className={isActive('/schedules')}>Schedules</Link>
        </li>
        <li>
          <Link to="/notifications" className={isActive('/notifications')}>Notifications</Link>
        </li>
        <li>
          <Link to="/team" className={isActive('/team')}>Team</Link>
        </li>
      </ul>
    </nav>
  );
}

function App() {
  const [setupDone, setSetupDone] = useState(null); // null = loading

  useEffect(() => {
    setupApi.getStatus()
      .then((data) => setSetupDone(Boolean(data.setup_completed)))
      .catch(() => setSetupDone(false)); // on error, keep user in wizard flow
  }, []);

  if (setupDone === null) {
    return <div className="loading" style={{ marginTop: 80 }}>Loading…</div>;
  }

  if (!setupDone) {
    return <SetupWizard onSetupComplete={() => setSetupDone(true)} />;
  }

  return (
    <Router>
      <div className="app">
        <div className="sidebar">
          <h1>Script Manager</h1>
          <Navigation />
        </div>
        <div className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/folder-roots" element={<FolderRoots />} />
            <Route path="/scripts" element={<Scripts />} />
            <Route path="/scripts/:id" element={<ScriptDetail />} />
            <Route path="/tags" element={<Tags />} />
            <Route path="/search" element={<Search />} />
            <Route path="/monitors" element={<Monitors />} />
            <Route path="/schedules" element={<Schedules />} />
            <Route path="/notifications" element={<Notifications />} />
            <Route path="/team" element={<Team />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;
