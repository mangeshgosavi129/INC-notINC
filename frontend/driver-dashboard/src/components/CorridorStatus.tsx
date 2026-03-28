import React from 'react';
import { SignalIcon, QueueBar, theme } from '@inc/shared-ui';
import type { LiveIntersection } from '../types';

interface Props {
  intersections: LiveIntersection[];
  evLinkIndex: number;
  evStatus: string;
  startNode?: string | null;
  destinationNode?: string | null;
}

export const CorridorStatus: React.FC<Props> = ({ intersections, evLinkIndex, evStatus, startNode, destinationNode }) => {
  return (
    <div style={{ padding: '8px 16px' }}>
      <div style={{
        fontSize: 11, fontWeight: 600, color: theme.textSecondary,
        textTransform: 'uppercase', marginBottom: 8, letterSpacing: 0.5,
      }}>
        Corridor Intersections
      </div>
      {intersections.map((ix, i) => {
        const cleared = evStatus !== 'idle' && i < evLinkIndex;
        const waiting = evStatus === 'waiting_at_signal' && i === evLinkIndex;
        const ahead = i >= evLinkIndex && !waiting;

        let badge: { text: string; color: string; bg: string } = { text: 'AHEAD', color: theme.textMuted, bg: theme.border };
        if (cleared) badge = { text: 'CLEARED', color: theme.signalGreen, bg: theme.signalGreen + '20' };
        if (waiting) badge = { text: 'WAITING', color: theme.signalRed, bg: theme.signalRed + '20' };

        return (
          <div key={ix.intersection_id} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            padding: '8px 12px', marginBottom: 4, borderRadius: 8,
            background: theme.cardBg, border: `1px solid ${theme.border}`,
          }}>
            <SignalIcon state={ix.signal_state as any} size={28} />
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: theme.textPrimary }}>
                  {ix.name}
                </div>
                {ix.intersection_id === startNode && <span style={{ fontSize: 9, padding: '2px 6px', background: theme.signalGreen + '20', color: theme.signalGreen, borderRadius: 4, fontWeight: 700 }}>START</span>}
                {ix.intersection_id === destinationNode && <span style={{ fontSize: 9, padding: '2px 6px', background: theme.accent + '20', color: theme.accent, borderRadius: 4, fontWeight: 700 }}>DEST</span>}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                <QueueBar queue={ix.total_queue} width={60} height={6} />
                <span style={{ fontSize: 10, color: theme.textMuted }}>{ix.total_queue.toFixed(0)} veh</span>
              </div>
            </div>
            <span style={{
              fontSize: 10, fontWeight: 700, padding: '2px 8px', borderRadius: 4,
              background: badge.bg, color: badge.color,
            }}>
              {badge.text}
            </span>
          </div>
        );
      })}
    </div>
  );
};
