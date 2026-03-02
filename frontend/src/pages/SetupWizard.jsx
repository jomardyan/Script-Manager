import { useState } from 'react';
import { setupApi } from '../services/api';

const STEPS = {
  WELCOME: 'welcome',
  DATABASE: 'database',
  ADMIN: 'admin',
  DONE: 'done',
};

const DB_TYPES = [
  { value: 'sqlite', label: 'SQLite (Local file — recommended for single-server)', icon: '🗄️' },
  { value: 'mysql', label: 'MySQL / MariaDB', icon: '🐬' },
  { value: 'postgresql', label: 'PostgreSQL', icon: '🐘' },
];

const MODES = [
  {
    value: 'demo',
    label: 'Demo Mode',
    icon: '🎮',
    description: 'Explore the app instantly with pre-loaded sample scripts and tags. No configuration required.',
    color: '#2ecc71',
  },
  {
    value: 'production',
    label: 'Production Setup',
    icon: '🚀',
    description: 'Full installation for real-world use. Configure your database and create an admin account.',
    color: '#3498db',
  },
  {
    value: 'development',
    label: 'Development Mode',
    icon: '🛠️',
    description: 'Quick setup for developers. Uses SQLite with relaxed defaults — great for testing.',
    color: '#9b59b6',
  },
];

function StepIndicator({ currentStep, mode }) {
  const steps =
    mode === 'demo'
      ? [{ key: STEPS.WELCOME, label: 'Welcome' }, { key: STEPS.DONE, label: 'Done' }]
      : [
          { key: STEPS.WELCOME, label: 'Welcome' },
          { key: STEPS.DATABASE, label: 'Database' },
          { key: STEPS.ADMIN, label: 'Admin Account' },
          { key: STEPS.DONE, label: 'Done' },
        ];

  const activeIndex = steps.findIndex((s) => s.key === currentStep);

  return (
    <div className="wizard-steps">
      {steps.map((step, idx) => (
        <div
          key={step.key}
          className={`wizard-step ${idx < activeIndex ? 'completed' : ''} ${idx === activeIndex ? 'active' : ''}`}
        >
          <div className="wizard-step-circle">{idx < activeIndex ? '✓' : idx + 1}</div>
          <span className="wizard-step-label">{step.label}</span>
          {idx < steps.length - 1 && <div className={`wizard-step-line ${idx < activeIndex ? 'completed' : ''}`} />}
        </div>
      ))}
    </div>
  );
}

function WelcomeStep({ onModeSelect }) {
  return (
    <div className="wizard-step-content">
      <div className="wizard-hero">
        <div className="wizard-logo">📋</div>
        <h1>Welcome to Script Manager</h1>
        <p className="wizard-subtitle">
          Let's get you set up in just a few steps. Choose how you'd like to start:
        </p>
      </div>

      <div className="wizard-mode-grid">
        {MODES.map((mode) => (
          <button
            key={mode.value}
            className="wizard-mode-card"
            style={{ '--mode-color': mode.color }}
            onClick={() => onModeSelect(mode.value)}
          >
            <div className="wizard-mode-icon">{mode.icon}</div>
            <h3>{mode.label}</h3>
            <p>{mode.description}</p>
            <span className="wizard-mode-cta" style={{ color: mode.color }}>
              Select →
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

function DatabaseStep({ dbConfig, setDbConfig, onTest, testResult, testing, onNext, onBack }) {
  const selectedType = DB_TYPES.find((t) => t.value === dbConfig.type);

  return (
    <div className="wizard-step-content">
      <h2>Database Configuration</h2>
      <p className="wizard-section-desc">
        Choose where Script Manager should store its data.
      </p>

      <div className="wizard-db-types">
        {DB_TYPES.map((dt) => (
          <label key={dt.value} className={`wizard-db-option ${dbConfig.type === dt.value ? 'selected' : ''}`}>
            <input
              type="radio"
              name="dbType"
              value={dt.value}
              checked={dbConfig.type === dt.value}
              onChange={() => setDbConfig({ ...dbConfig, type: dt.value })}
            />
            <span className="wizard-db-icon">{dt.icon}</span>
            <span>{dt.label}</span>
          </label>
        ))}
      </div>

      {dbConfig.type === 'sqlite' && (
        <div className="wizard-db-form">
          <div className="form-group">
            <label>Database File Path</label>
            <input
              type="text"
              placeholder="./data/scripts.db"
              value={dbConfig.sqlite_path || ''}
              onChange={(e) => setDbConfig({ ...dbConfig, sqlite_path: e.target.value })}
            />
            <small>Leave blank to use the default path (<code>./data/scripts.db</code>).</small>
          </div>
        </div>
      )}

      {(dbConfig.type === 'mysql' || dbConfig.type === 'postgresql') && (
        <div className="wizard-db-form">
          <div className="wizard-db-form-grid">
            <div className="form-group">
              <label>Host</label>
              <input
                type="text"
                placeholder="localhost"
                value={dbConfig.host || ''}
                onChange={(e) => setDbConfig({ ...dbConfig, host: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Port</label>
              <input
                type="number"
                placeholder={dbConfig.type === 'mysql' ? '3306' : '5432'}
                value={dbConfig.port || ''}
                onChange={(e) => setDbConfig({ ...dbConfig, port: e.target.value === '' ? undefined : parseInt(e.target.value, 10) })}
              />
            </div>
          </div>
          <div className="form-group">
            <label>Database Name</label>
            <input
              type="text"
              placeholder="script_manager"
              value={dbConfig.database_name || ''}
              onChange={(e) => setDbConfig({ ...dbConfig, database_name: e.target.value })}
            />
          </div>
          <div className="wizard-db-form-grid">
            <div className="form-group">
              <label>Username</label>
              <input
                type="text"
                placeholder="root"
                value={dbConfig.username || ''}
                onChange={(e) => setDbConfig({ ...dbConfig, username: e.target.value })}
              />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input
                type="password"
                placeholder="••••••••"
                value={dbConfig.password || ''}
                onChange={(e) => setDbConfig({ ...dbConfig, password: e.target.value })}
              />
            </div>
          </div>

          <div className="wizard-test-row">
            <button className="button button-secondary" onClick={onTest} disabled={testing}>
              {testing ? 'Testing…' : '🔌 Test Connection'}
            </button>
            {testResult && (
              <span className={`wizard-test-result ${testResult.success ? 'success' : 'fail'}`}>
                {testResult.success ? '✅' : '❌'} {testResult.message}
              </span>
            )}
          </div>

          <div className="wizard-db-notice">
            <strong>Note:</strong> MySQL and PostgreSQL support requires additional driver packages
            (<code>aiomysql</code> / <code>asyncpg</code>) and a server restart after setup. The app
            currently ships with SQLite and will continue using it until you migrate.
          </div>
        </div>
      )}

      <div className="wizard-actions">
        <button className="button button-secondary" onClick={onBack}>← Back</button>
        <button className="button" onClick={onNext}>Next →</button>
      </div>
    </div>
  );
}

function AdminStep({ adminConfig, setAdminConfig, errors, onNext, onBack }) {
  return (
    <div className="wizard-step-content">
      <h2>Create Admin Account</h2>
      <p className="wizard-section-desc">
        This account will have full administrative access to Script Manager.
      </p>

      <div className="wizard-admin-form">
        <div className="wizard-db-form-grid">
          <div className="form-group">
            <label>Username *</label>
            <input
              type="text"
              placeholder="admin"
              value={adminConfig.username}
              onChange={(e) => setAdminConfig({ ...adminConfig, username: e.target.value })}
            />
            {errors.username && <span className="wizard-field-error">{errors.username}</span>}
          </div>
          <div className="form-group">
            <label>Full Name</label>
            <input
              type="text"
              placeholder="Alice Smith"
              value={adminConfig.full_name}
              onChange={(e) => setAdminConfig({ ...adminConfig, full_name: e.target.value })}
            />
          </div>
        </div>

        <div className="form-group">
          <label>Email Address *</label>
          <input
            type="email"
            placeholder="admin@example.com"
            value={adminConfig.email}
            onChange={(e) => setAdminConfig({ ...adminConfig, email: e.target.value })}
          />
          {errors.email && <span className="wizard-field-error">{errors.email}</span>}
        </div>

        <div className="wizard-db-form-grid">
          <div className="form-group">
            <label>Password *</label>
            <input
              type="password"
              placeholder="Min 8 characters"
              value={adminConfig.password}
              onChange={(e) => setAdminConfig({ ...adminConfig, password: e.target.value })}
            />
            {errors.password && <span className="wizard-field-error">{errors.password}</span>}
          </div>
          <div className="form-group">
            <label>Confirm Password *</label>
            <input
              type="password"
              placeholder="Repeat password"
              value={adminConfig.confirmPassword}
              onChange={(e) => setAdminConfig({ ...adminConfig, confirmPassword: e.target.value })}
            />
            {errors.confirmPassword && (
              <span className="wizard-field-error">{errors.confirmPassword}</span>
            )}
          </div>
        </div>
      </div>

      <div className="wizard-actions">
        <button className="button button-secondary" onClick={onBack}>← Back</button>
        <button className="button" onClick={onNext}>Finish Setup →</button>
      </div>
    </div>
  );
}

function DoneStep({ mode, onEnter }) {
  const modeInfo = MODES.find((m) => m.value === mode) || MODES[1];
  return (
    <div className="wizard-step-content wizard-done">
      <div className="wizard-done-icon">🎉</div>
      <h2>Setup Complete!</h2>
      <p className="wizard-section-desc">
        Script Manager is configured in <strong>{modeInfo.label}</strong> mode and ready to use.
      </p>

      {mode === 'demo' && (
        <div className="wizard-done-notice">
          Sample scripts, tags, and a demo folder root have been pre-loaded so you can explore
          immediately. Switch to <em>Production Setup</em> whenever you're ready to use real data.
        </div>
      )}

      {mode === 'development' && (
        <div className="wizard-done-notice">
          Development mode is active. The app uses SQLite with relaxed defaults. Change the mode
          via the setup API (<code>POST /api/setup/complete</code>) when you're ready to deploy.
        </div>
      )}

      <button className="button wizard-enter-btn" onClick={onEnter}>
        {modeInfo.icon} Enter Script Manager
      </button>
    </div>
  );
}

export default function SetupWizard({ onSetupComplete }) {
  const [step, setStep] = useState(STEPS.WELCOME);
  const [mode, setMode] = useState(null);
  const [dbConfig, setDbConfig] = useState({ type: 'sqlite' });
  const [adminConfig, setAdminConfig] = useState({
    username: '',
    email: '',
    password: '',
    confirmPassword: '',
    full_name: '',
  });
  const [adminErrors, setAdminErrors] = useState({});
  const [testResult, setTestResult] = useState(null);
  const [testing, setTesting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);

  const handleModeSelect = async (selectedMode) => {
    setMode(selectedMode);
    setSubmitError(null);

    if (selectedMode === 'demo') {
      // Skip configuration — activate demo right away
      setSubmitting(true);
      try {
        await setupApi.activateDemo();
        setStep(STEPS.DONE);
      } catch (err) {
        setSubmitError(err.message);
      } finally {
        setSubmitting(false);
      }
    } else {
      setStep(STEPS.DATABASE);
    }
  };

  const handleTestDb = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const data = await setupApi.testDb(dbConfig);
      setTestResult(data);
    } catch (err) {
      setTestResult({ success: false, message: err.message });
    } finally {
      setTesting(false);
    }
  };

  const handleDbNext = () => {
    // For external databases, require a successful connection test before continuing.
    if (dbConfig.type === 'mysql' || dbConfig.type === 'postgresql') {
      if (!testResult || !testResult.success) {
        setTestResult((prev) => {
          if (prev && prev.success === false && prev.message) return prev;
          return {
            success: false,
            message: 'Please test the database connection and resolve any issues before continuing.',
          };
        });
        return;
      }
    }
    setStep(STEPS.ADMIN);
  };

  const validateAdmin = () => {
    const errs = {};
    if (!adminConfig.username.trim()) errs.username = 'Username is required';
    if (!adminConfig.email.trim()) errs.email = 'Email is required';
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(adminConfig.email))
      errs.email = 'Invalid email address';
    if (!adminConfig.password) errs.password = 'Password is required';
    else if (adminConfig.password.length < 8) errs.password = 'Password must be at least 8 characters';
    if (adminConfig.password !== adminConfig.confirmPassword)
      errs.confirmPassword = 'Passwords do not match';
    return errs;
  };

  const handleAdminNext = async () => {
    const errs = validateAdmin();
    if (Object.keys(errs).length > 0) {
      setAdminErrors(errs);
      return;
    }
    setAdminErrors({});
    setSubmitting(true);
    setSubmitError(null);

    try {
      const payload = {
        mode,
        database: dbConfig,
        admin: {
          username: adminConfig.username,
          email: adminConfig.email,
          password: adminConfig.password,
          full_name: adminConfig.full_name || null,
        },
      };
      await setupApi.complete(payload);
      setStep(STEPS.DONE);
    } catch (err) {
      setSubmitError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="wizard-overlay">
      <div className="wizard-container">
        {/* Header */}
        <div className="wizard-header">
          <span className="wizard-brand">📋 Script Manager</span>
          <span className="wizard-tagline">Installation Wizard</span>
        </div>

        {/* Step indicator — only after mode is chosen */}
        {mode && step !== STEPS.WELCOME && (
          <StepIndicator currentStep={step} mode={mode} />
        )}

        {/* Content */}
        <div className="wizard-body">
          {submitError && (
            <div className="error" style={{ marginBottom: 16 }}>
              {submitError}
            </div>
          )}
          {submitting && (
            <div className="wizard-submitting">
              <div className="wizard-spinner" />
              <span>Applying configuration…</span>
            </div>
          )}
          {!submitting && (
            <>
              {step === STEPS.WELCOME && <WelcomeStep onModeSelect={handleModeSelect} />}
              {step === STEPS.DATABASE && (
                <DatabaseStep
                  dbConfig={dbConfig}
                  setDbConfig={setDbConfig}
                  onTest={handleTestDb}
                  testResult={testResult}
                  testing={testing}
                  onNext={handleDbNext}
                  onBack={() => setStep(STEPS.WELCOME)}
                />
              )}
              {step === STEPS.ADMIN && (
                <AdminStep
                  adminConfig={adminConfig}
                  setAdminConfig={setAdminConfig}
                  errors={adminErrors}
                  onNext={handleAdminNext}
                  onBack={() => setStep(STEPS.DATABASE)}
                />
              )}
              {step === STEPS.DONE && (
                <DoneStep mode={mode} onEnter={onSetupComplete} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
