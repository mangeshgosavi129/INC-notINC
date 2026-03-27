import React from 'react';
import { theme } from '@inc/shared-ui';
import type { Alert } from '../types';

interface Props {
  alerts: Alert[];
  onUnblock?: (from: string, to: string) => void;
}

export const EventPanel: React.FC<Props> = ({ alerts, onUnblock }) => {
  const blockages = alerts.filter((a) => a.type === 'blockage');

  if (blockages.length === 0) {
    return (
      <div style={{ padding: 12, color: theme.textMuted, fontSize: 12, textAlign: 'center' }}>
        No active events
      </div>
    );
  }

  return (
    <div style={{ padding: 8 }}>
      <div style={{ fontSize: 11, fontWeight: 600, color: theme.textSecondary, marginBottom: 6, textTransform: 'uppercase' }}>
        Active Events
      </div>
      {blockages.map((a, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '6px 10px', marginBottom: 4, borderRadius: 6,
          background: theme.signalRed + '10', border: `1px solid ${theme.signalRed}30`,
        }}>
          <div>
            <span style={{ fontSize: 12, color: theme.signalRed, fontWeight: 600 }}>Blockage</span>
            <span style={{ fontSize: 11, color: theme.textSecondary, marginLeft: 8 }}>
              {a.from} → {a.to}
            </span>
          </div>
          {onUnblock && a.from && a.to && (
            <button
              onClick={() => onUnblock(a.from!, a.to!)}
              style={{
                padding: '2px 10px', border: 'none', borderRadius: 4,
                background: theme.signalRed, color: '#fff', fontSize: 10,
                cursor: 'pointer', fontWeight: 600,
              }}
            >
              Unblock
            </button>
          )}
        </div>
      ))}
    </div>
  );
};
