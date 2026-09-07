import { useCallback, useEffect, useState } from 'react';

const STORAGE_KEY = 'script-manager.theme';
const MODES = ['system', 'light', 'dark'];
const LABELS = { system: 'System theme', light: 'Light theme', dark: 'Dark theme' };
const ICONS = { system: '◑', light: '☀', dark: '☽' };

function readStored() {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return MODES.includes(value) ? value : 'system';
  } catch {
    return 'system';
  }
}

/**
 * Light / dark / follow-the-OS switch.
 *
 * "system" leaves the root element unmarked so the `prefers-color-scheme`
 * media query in index.css decides; an explicit choice stamps data-theme,
 * which the stylesheet honours over the media query in both directions.
 */
export default function ThemeToggle() {
  const [mode, setMode] = useState(readStored);

  useEffect(() => {
    const root = document.documentElement;
    if (mode === 'system') root.removeAttribute('data-theme');
    else root.setAttribute('data-theme', mode);

    try {
      window.localStorage.setItem(STORAGE_KEY, mode);
    } catch {
      /* storage unavailable; the choice still applies for this page load */
    }
  }, [mode]);

  const cycle = useCallback(() => {
    setMode((current) => MODES[(MODES.indexOf(current) + 1) % MODES.length]);
  }, []);

  return (
    <button
      type="button"
      className="button button-ghost button--small"
      onClick={cycle}
      title={`${LABELS[mode]} (click to change)`}
      aria-label={`${LABELS[mode]}. Activate to change theme.`}
    >
      <span aria-hidden="true">{ICONS[mode]}</span>
      <span>{mode === 'system' ? 'Auto' : LABELS[mode].replace(' theme', '')}</span>
    </button>
  );
}
