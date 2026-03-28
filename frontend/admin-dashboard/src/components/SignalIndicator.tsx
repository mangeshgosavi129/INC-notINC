import React from 'react';
import { SignalIcon, theme } from '@inc/shared-ui';
import type { IntersectionState } from '../types';

interface Props {
  intersection: IntersectionState;
  compact?: boolean;
}

export const SignalIndicator: React.FC<Props> = ({ intersection, compact }) => {
  const totalQueue = Object.values(intersection.queues).reduce((a, b) => a + b, 0);

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: compact ? '4px 8px' : '6px 12px',
      background: theme.cardBg, borderRadius: 6, border: `1px solid ${theme.border}`,
    }}>
      <SignalIcon state={intersection.state} size={compact ? 24 : 32} />
      <div>
        <div style={{ fontSize: compact ? 11 : 13, fontWeight: 600, color: theme.textPrimary }}>
          {intersection.intersection_id}
        </div>
        <div style={{ fontSize: 10, color: theme.textSecondary }}>
          P{intersection.phase} | Q: {totalQueue.toFixed(0)}
        </div>
      </div>
      {!compact && intersection.green_movements.length > 0 && (
        <div style={{ display: 'flex', gap: 3, marginLeft: 4 }}>
          {intersection.green_movements.map((m) => (
            <span key={m} style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 3,
              background: theme.signalGreen + '20', color: theme.signalGreen,
            }}>
              {m}
            </span>
          ))}
        </div>
      )}
    </div>
  );
};
