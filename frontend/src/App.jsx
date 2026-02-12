import { BrowserRouter as Router, Routes, Route, Link, useLocation } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import FolderRoots from './pages/FolderRoots';
import Scripts from './pages/Scripts';
import ScriptDetail from './pages/ScriptDetail';
import Tags from './pages/Tags';
import Search from './pages/Search';

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
      </ul>
    </nav>
  );
}

function App() {
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
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;
