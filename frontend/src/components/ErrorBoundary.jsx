import { Component } from 'react';

/**
 * Catches render-time exceptions.
 *
 * Without a boundary a single throw anywhere in the tree unmounted the whole
 * application and left the user staring at a blank white page with no clue
 * what happened and no way back.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the stack in the console for whoever is debugging.
    console.error('Unhandled render error:', error, info?.componentStack);
  }

  render() {
    const { error } = this.state;
    const { children, fallbackTitle = 'Something went wrong' } = this.props;

    if (!error) return children;

    return (
      <div className="error-boundary" role="alert">
        <h2>{fallbackTitle}</h2>
        <p>
          The page could not be displayed. The details below may help when reporting
          the problem.
        </p>
        <pre className="error-boundary__detail">{String(error?.message || error)}</pre>
        <div className="error-boundary__actions">
          <button
            type="button"
            className="button"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
          <button
            type="button"
            className="button button-secondary"
            onClick={() => window.location.assign('/')}
          >
            Back to dashboard
          </button>
        </div>
      </div>
    );
  }
}
