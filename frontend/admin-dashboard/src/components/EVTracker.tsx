import React from 'react';
import { theme } from '@inc/shared-ui';
import type { EVState } from '../types';

interface Props {
  ev: EVState | null;
  intersectionIds?: string[];
  linkDistances?: number[];
}

export const EVTracker: React.FC<Props> = ({
  ev,
  intersectionIds = ['INT_01', 'INT_02', 'INT_03', 'INT_04', 'INT_05'],
  linkDistances = [450, 520, 380, 500],
}) => {
  if (!ev) {
    return (
      <div style={{ padding: 12, color: theme.textMuted, fontSize: 13, textAlign: 'center' }}>
        No EV dispatched
      </div>
    );
  }

  const totalDist = linkDistances.reduce((a, b) => a + b, 0);
  const waypointPcts: number[] = [0];
  let cum = 0;
  for (const d of linkDistances) {
    cum += d;
    waypointPcts.push((cum / totalDist) * 100);
  }

  // EV progress as percentage
  let progressPct = 0;
  if (ev.status === 'arrived') {
    progressPct = 100;
  } else if (ev.current_link_index < linkDistances.length) {
    const prevDist = linkDistances.slice(0, ev.current_link_index).reduce((a, b) => a + b, 0);
    progressPct = ((prevDist + linkDistances[ev.current_link_index] * ev.position_on_link) / totalDist) * 100;
  }

  const statusColor = ev.status === 'waiting_at_signal' ? theme.signalRed
    : ev.status === 'arrived' ? theme.signalGreen
    : theme.accent;

  return (
    <div style={{ padding: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: theme.textPrimary }}>
          EV: {ev.ev_id}
        </span>
        <span style={{
          fontSize: 11, padding: '1px 8px', borderRadius: 4,
          background: statusColor + '20', color: statusColor,
        }}>
          {ev.status.replace(/_/g, ' ').toUpperCase()}
        </span>
      </div>

      {/* Progress bar */}
      <div style={{ position: 'relative', height: 30, marginBottom: 8 }}>
        {/* Track */}
        <div style={{
          position: 'absolute', top: 12, left: 0, right: 0, height: 6,
          background: theme.border, borderRadius: 3,
        }} />
        {/* Fill */}
        <div style={{
          position: 'absolute', top: 12, left: 0, height: 6,
          width: `${progressPct}%`, background: theme.accent, borderRadius: 3,
          transition: 'width 0.5s ease',
        }} />
        {/* Waypoints */}
        {waypointPcts.map((pct, i) => {
          const cleared = progressPct > pct + 1;
          return (
            <div key={i} style={{
              position: 'absolute', left: `${pct}%`, top: 6,
              width: 18, height: 18, borderRadius: '50%', transform: 'translateX(-9px)',
              background: cleared ? theme.signalGreen : theme.cardBg,
              border: `2px solid ${cleared ? theme.signalGreen : theme.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 8, color: cleared ? '#fff' : theme.textMuted, fontWeight: 700,
            }}>
              {i + 1}
            </div>
          );
        })}
      </div>

      {/* Labels */}
      <div style={{ position: 'relative', height: 16 }}>
        {waypointPcts.map((pct, i) => (
          <span key={i} style={{
            position: 'absolute', left: `${pct}%`, transform: 'translateX(-50%)',
            fontSize: 9, color: theme.textMuted, whiteSpace: 'nowrap',
          }}>
            {intersectionIds[i]?.replace('INT_', 'I')}
          </span>
        ))}
      </div>

      {/* Stats */}
      <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, color: theme.textSecondary }}>
        <span>Delay: {ev.total_delay.toFixed(1)}s</span>
        {ev.waiting_at && <span style={{ color: theme.signalRed }}>Waiting at: {ev.waiting_at}</span>}
      </div>
    </div>
  );
};
