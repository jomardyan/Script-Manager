import { useEffect, useId } from 'react';

/**
 * Small shared building blocks.
 *
 * Before this the pages carried 100+ inline style objects and duplicated the
 * same badge, empty-state and form markup, so the app looked different from
 * page to page and no label was associated with its input.
 */

// ── Forms ─────────────────────────────────────────────────────────────────────

/**
 * A labelled form control. Clones the child so the label's htmlFor and the
 * control's id always match without every caller inventing unique ids.
 */
export function Field({ label, hint, error, required, children, className = '' }) {
  const id = useId();
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ');

  return (
    <div className={`field ${className}`.trim()}>
      <label className="field__label" htmlFor={id}>
        {label}
        {required && <span className="field__required" aria-hidden="true"> *</span>}
      </label>
      {typeof children === 'function'
        ? children({ id, 'aria-describedby': describedBy || undefined, 'aria-invalid': error ? true : undefined })
        : children}
      {hint && <p className="field__hint" id={hintId}>{hint}</p>}
      {error && <p className="field__error" id={errorId}>{error}</p>}
    </div>
  );
}

/** A checkbox with its label, wired up for keyboard and screen-reader users. */
export function Checkbox({ label, hint, checked, onChange, disabled, name }) {
  const id = useId();
  return (
    <div className="checkbox">
      <input
        id={id}
        name={name}
        type="checkbox"
        checked={Boolean(checked)}
        onChange={(event) => onChange(event.target.checked)}
        disabled={disabled}
        aria-describedby={hint ? `${id}-hint` : undefined}
      />
      <div>
        <label htmlFor={id}>{label}</label>
        {hint && <p className="field__hint" id={`${id}-hint`}>{hint}</p>}
      </div>
    </div>
  );
}

// ── Status display ────────────────────────────────────────────────────────────

/**
 * A status pill. Tone drives more than hue (weight, border, dot) so the state
 * is still readable without colour vision.
 */
export function Badge({ tone = 'neutral', children, title }) {
  return (
    <span className={`badge badge--${tone}`} title={title}>
      <span className="badge__dot" aria-hidden="true" />
      {children}
    </span>
  );
}

export const STATUS_TONES = {
  active: 'success',
  ok: 'success',
  success: 'success',
  resolved: 'success',
  enabled: 'success',
  running: 'info',
  new: 'neutral',
  draft: 'neutral',
  unknown: 'neutral',
  disabled: 'neutral',
  inactive: 'neutral',
  paused: 'warning',
  acknowledged: 'warning',
  warning: 'warning',
  deprecated: 'warning',
  timeout: 'warning',
  archived: 'neutral',
  failing: 'danger',
  failed: 'danger',
  open: 'danger',
  critical: 'danger',
};

export function StatusBadge({ status, fallback = 'unknown' }) {
  const value = status || fallback;
  return <Badge tone={STATUS_TONES[value] || 'neutral'}>{value}</Badge>;
}

// ── Page furniture ────────────────────────────────────────────────────────────

/** Page heading. Also keeps document.title in step with the current view. */
export function PageHeader({ title, description, actions }) {
  useEffect(() => {
    const previous = document.title;
    document.title = `${title} · Script Manager`;
    return () => { document.title = previous; };
  }, [title]);

  return (
    <header className="page-header">
      <div>
        <h2>{title}</h2>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="page-header__actions">{actions}</div>}
    </header>
  );
}

export function Card({ title, description, actions, children, className = '' }) {
  return (
    <section className={`card ${className}`.trim()}>
      {(title || actions) && (
        <div className="card__header">
          <div>
            {title && <h3>{title}</h3>}
            {description && <p className="card__description">{description}</p>}
          </div>
          {actions && <div className="card__actions">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ title, description, action, icon = '∅' }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon" aria-hidden="true">{icon}</div>
      <p className="empty-state__title">{title}</p>
      {description && <p className="empty-state__description">{description}</p>}
      {action && <div className="empty-state__action">{action}</div>}
    </div>
  );
}

/**
 * A dismissible error banner with a retry.
 *
 * Pages used to replace their entire content with an error string, leaving no
 * way to retry or to get back to the rest of the page.
 */
export function ErrorBanner({ message, onRetry, onDismiss }) {
  if (!message) return null;
  return (
    <div className="banner banner--error" role="alert">
      <span className="banner__message">{message}</span>
      <span className="banner__actions">
        {onRetry && (
          <button type="button" className="button button-secondary button--small" onClick={onRetry}>
            Retry
          </button>
        )}
        {onDismiss && (
          <button type="button" className="icon-button" onClick={onDismiss} aria-label="Dismiss error">
            ×
          </button>
        )}
      </span>
    </div>
  );
}

/** Placeholder rows shown while data loads, instead of blanking the page. */
export function TableSkeleton({ rows = 5, columns = 4 }) {
  return (
    <div className="skeleton-table" aria-hidden="true">
      {Array.from({ length: rows }).map((_, rowIndex) => (
        // eslint-disable-next-line react/no-array-index-key
        <div className="skeleton-row" key={rowIndex}>
          {Array.from({ length: columns }).map((__, colIndex) => (
            // eslint-disable-next-line react/no-array-index-key
            <span className="skeleton-cell" key={colIndex} />
          ))}
        </div>
      ))}
    </div>
  );
}

export function Spinner({ label = 'Loading' }) {
  return (
    <div className="spinner-wrap" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" />
      <span className="spinner__label">{label}…</span>
    </div>
  );
}

// ── Tables ────────────────────────────────────────────────────────────────────

/**
 * A sortable column header.
 *
 * Sorting used to live in a separate dropdown, so the table headers themselves
 * were inert and the current sort was invisible to assistive technology.
 */
export function SortableHeader({ column, label, sortBy, sortOrder, onSort, align }) {
  const isActive = sortBy === column;
  const ariaSort = isActive ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none';
  return (
    <th aria-sort={ariaSort} className={align ? `text-${align}` : undefined}>
      <button
        type="button"
        className={`sort-button${isActive ? ' sort-button--active' : ''}`}
        onClick={() => onSort(column)}
      >
        {label}
        <span className="sort-button__arrow" aria-hidden="true">
          {isActive ? (sortOrder === 'asc' ? '▲' : '▼') : '↕'}
        </span>
      </button>
    </th>
  );
}

export function Pagination({ page, totalPages, total, pageSize, onChange }) {
  if (!totalPages || totalPages <= 1) return null;
  const first = (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav className="pagination" aria-label="Pagination">
      <button
        type="button"
        className="button button-secondary button--small"
        onClick={() => onChange(Math.max(1, page - 1))}
        disabled={page <= 1}
      >
        Previous
      </button>
      <span className="pagination__status" aria-live="polite">
        {total > 0 ? `${first}–${last} of ${total}` : 'No results'}
        <span className="pagination__page">Page {page} of {totalPages}</span>
      </span>
      <button
        type="button"
        className="button button-secondary button--small"
        onClick={() => onChange(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages}
      >
        Next
      </button>
    </nav>
  );
}

/** Tag chip. The remove affordance is a real button so it is keyboard-reachable. */
export function TagChip({ name, color, onRemove }) {
  return (
    <span className="tag" style={color ? { backgroundColor: color } : undefined}>
      {name}
      {onRemove && (
        <button
          type="button"
          className="tag__remove"
          onClick={onRemove}
          aria-label={`Remove tag ${name}`}
        >
          ×
        </button>
      )}
    </span>
  );
}

/** Button that shows and enforces its own in-flight state. */
export function BusyButton({ busy, children, busyLabel = 'Working…', className = 'button', ...rest }) {
  return (
    <button type="button" className={className} disabled={busy || rest.disabled} {...rest}>
      {busy ? (
        <>
          <span className="spinner spinner--inline" aria-hidden="true" />
          {busyLabel}
        </>
      ) : children}
    </button>
  );
}
