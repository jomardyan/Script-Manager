import { useEffect, useId, useRef } from 'react';

const FOCUSABLE = [
  'a[href]', 'button:not([disabled])', 'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])', 'textarea:not([disabled])', '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * Accessible dialog.
 *
 * The previous modals were plain divs: no dialog role, no Escape key, no focus
 * management, and the background stayed scrollable and tabbable behind them.
 */
export default function Modal({
  title,
  description,
  onClose,
  children,
  footer,
  size = 'medium',
  closeLabel = 'Close dialog',
}) {
  const titleId = useId();
  const descriptionId = useId();
  const dialogRef = useRef(null);
  const previouslyFocused = useRef(null);

  // Callers pass onClose as an inline arrow, so it is a new function on every
  // parent render. Reading it through a ref keeps the effect below from
  // re-running (and yanking focus out of whatever the user is typing in)
  // whenever something unrelated, such as a toast, re-renders the page.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    previouslyFocused.current = document.activeElement;

    // Move focus into the dialog so keyboard and screen-reader users land inside it.
    const node = dialogRef.current;
    const first = node?.querySelector(FOCUSABLE);
    (first || node)?.focus();

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const onKeyDown = (event) => {
      if (event.key === 'Escape') {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== 'Tab' || !node) return;

      // Keep Tab inside the dialog rather than letting it wander behind the overlay.
      const focusable = Array.from(node.querySelectorAll(FOCUSABLE))
        .filter((el) => el.offsetParent !== null || el === document.activeElement);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }
      const firstEl = focusable[0];
      const lastEl = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === firstEl) {
        event.preventDefault();
        lastEl.focus();
      } else if (!event.shiftKey && document.activeElement === lastEl) {
        event.preventDefault();
        firstEl.focus();
      }
    };

    document.addEventListener('keydown', onKeyDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.body.style.overflow = previousOverflow;
      // Return focus to whatever opened the dialog.
      if (previouslyFocused.current && previouslyFocused.current.focus) {
        previouslyFocused.current.focus();
      }
    };
    // Deliberately empty: the dialog sets up focus handling once, on mount.
  }, []);

  return (
    <div
      className="modal-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={`modal modal--${size}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={description ? descriptionId : undefined}
        tabIndex={-1}
        ref={dialogRef}
      >
        <div className="modal__header">
          <div>
            <h2 id={titleId}>{title}</h2>
            {description && <p id={descriptionId} className="modal__description">{description}</p>}
          </div>
          <button type="button" className="icon-button" onClick={onClose} aria-label={closeLabel}>
            ×
          </button>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__footer">{footer}</div>}
      </div>
    </div>
  );
}
