import { useCallback, useState } from 'react';
import Modal from './Modal';

/**
 * A confirmation dialog that can state the consequence of an action.
 *
 * `window.confirm` could only render a bare sentence, blocked the page, and
 * gave no room to say what a destructive action would actually affect.
 */
export default function ConfirmDialog({
  title,
  message,
  detail,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  tone = 'danger',
  busy = false,
  onConfirm,
  onCancel,
}) {
  return (
    <Modal title={title} onClose={busy ? () => {} : onCancel} size="small">
      <p className="confirm__message">{message}</p>
      {detail && <p className="confirm__detail">{detail}</p>}
      <div className="modal__footer">
        <button type="button" className="button button-secondary" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={tone === 'danger' ? 'button button-danger' : 'button'}
          onClick={onConfirm}
          disabled={busy}
        >
          {busy ? 'Working…' : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}

/**
 * Hook wrapping the dialog so a caller can `await confirm({...})` in a handler
 * exactly where `window.confirm` used to sit.
 */
export function useConfirm() {
  const [request, setRequest] = useState(null);
  const [busy, setBusy] = useState(false);

  const confirm = useCallback((options) => new Promise((resolve) => {
    setRequest({ ...options, resolve });
  }), []);

  const close = useCallback((result) => {
    setRequest((current) => {
      if (current) current.resolve(result);
      return null;
    });
    setBusy(false);
  }, []);

  const element = request ? (
    <ConfirmDialog
      title={request.title || 'Are you sure?'}
      message={request.message}
      detail={request.detail}
      confirmLabel={request.confirmLabel}
      cancelLabel={request.cancelLabel}
      tone={request.tone}
      busy={busy}
      onConfirm={() => {
        setBusy(true);
        close(true);
      }}
      onCancel={() => close(false)}
    />
  ) : null;

  return { confirm, confirmElement: element };
}
