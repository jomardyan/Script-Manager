import { Link } from 'react-router-dom';

/**
 * Multi-select for notification channels.
 *
 * Monitors and scheduled jobs both accept `notify_channel_ids`, but neither
 * form offered any way to set it, so nothing could ever alert anyone.
 */
export default function ChannelPicker({ channels, value, onChange, label = 'Notify these channels' }) {
  const selected = value || [];

  const toggle = (id) => {
    onChange(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);
  };

  return (
    <fieldset>
      <legend>{label}</legend>
      {channels.length === 0 ? (
        <p className="text-muted text-small">
          No notification channels configured yet.{' '}
          <Link to="/notifications">Add one</Link> so failures actually reach someone.
        </p>
      ) : (
        <div className="check-grid scroll-box">
          {channels.map((channel) => (
            <div className="checkbox" key={channel.id}>
              <input
                id={`channel-${channel.id}`}
                type="checkbox"
                checked={selected.includes(channel.id)}
                onChange={() => toggle(channel.id)}
                disabled={!channel.enabled}
              />
              <label htmlFor={`channel-${channel.id}`}>
                {channel.name}
                <span className="text-muted text-small"> ({channel.type})</span>
                {!channel.enabled && <span className="text-muted text-small"> · disabled</span>}
              </label>
            </div>
          ))}
        </div>
      )}
    </fieldset>
  );
}
