import React, { useState, useEffect } from 'react';
import { theme } from '@inc/shared-ui';
import type { Alert } from '../types';

interface Props {
  alerts: Alert[];
}

export const AlertBanner: React.FC<Props> = ({ alerts }) => {
  const [dismissed, setDismissed] = useState<number>(0);

  // Reset dismissed when new alerts arrive
  useEffect(() => {
    if (alerts.length > dismissed) setDismissed(0);
  }, [alerts.length]);

  if (alerts.length === 0 || dismissed >= alerts.length) return null;

  // Show highest severity
  const critical = alerts.find((a) => a.severity === 'critical');
  const alert = critical ?? alerts[alerts.length - 1];
  const isCritical = alert.severity === 'critical';

  let message = '';
  if (alert.type === 'high_queue') {
    message = `High queue at ${alert.intersection_id}: ${alert.queue_length?.toFixed(0)} vehicles`;
  } else if (alert.type === 'ev_delay') {
    message = `EV delay: ${alert.total_delay?.toFixed(1)}s`;
  } else if (alert.type === 'blockage') {
    message = `Blockage: ${alert.from} → ${alert.to}`;
  }

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '8px 16px',
      background: isCritical ? theme.signalRed + '20' : theme.signalAmber + '20',
      borderBottom: `2px solid ${isCritical ? theme.signalRed : theme.signalAmber}`,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{
          fontSize: 10, fontWeight: 700, padding: '1px 6px', borderRadius: 3,
          background: isCritical ? theme.signalRed : theme.signalAmber,
          color: '#fff', textTransform: 'uppercase',
        }}>
          {alert.severity}
        </span>
        <span style={{ fontSize: 13, color: theme.textPrimary }}>{message}</span>
      </div>
      <button
        onClick={() => setDismissed(alerts.length)}
        style={{
          background: 'none', border: 'none', color: theme.textMuted,
          cursor: 'pointer', fontSize: 16, padding: '0 4px',
        }}
      >
        x
      </button>
    </div>
  );
};
