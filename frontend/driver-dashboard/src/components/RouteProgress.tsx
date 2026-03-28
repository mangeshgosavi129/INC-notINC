import React from 'react';
import { theme } from '@inc/shared-ui';

interface Props {
  progressPct: number;
  intersectionNames?: string[];
  linkDistances?: number[];
  startNode?: string | null;
  destinationNode?: string | null;
}

export const RouteProgress: React.FC<Props> = ({
  progressPct,
  intersectionNames = ['INT_01', 'INT_02', 'INT_03', 'INT_04', 'INT_05'],
  linkDistances = [450, 520, 380, 500],
  startNode,
  destinationNode,
}) => {
  const totalDist = linkDistances.reduce((a, b) => a + b, 0);
  const pcts: number[] = [0];
  let cum = 0;
  for (const d of linkDistances) {
    cum += d;
    pcts.push((cum / totalDist) * 100);
  }

  return (
    <div style={{ padding: '12px 20px' }}>
      <div style={{ position: 'relative', height: 44, marginBottom: 4 }}>
        {/* Track */}
        <div style={{
          position: 'absolute', top: 16, left: 0, right: 0, height: 8,
          background: theme.border, borderRadius: 4,
        }} />
        {/* Fill */}
        <div style={{
          position: 'absolute', top: 16, left: 0, height: 8,
          width: `${Math.min(progressPct, 100)}%`,
          background: `linear-gradient(90deg, ${theme.signalGreen}, ${theme.accent})`,
          borderRadius: 4, transition: 'width 0.5s ease',
        }} />
        {/* Waypoints */}
        {pcts.map((pct, i) => {
          const cleared = progressPct > pct + 1;
          const current = Math.abs(progressPct - pct) < 5;
          const isStart = i === 0 && startNode;
          const isDest = i === pcts.length - 1 && destinationNode;
          
          return (
            <div key={i} style={{
              position: 'absolute', left: `${pct}%`, top: 8,
              height: 24, padding: isStart || isDest ? '0 6px' : 0, 
              width: isStart || isDest ? 'auto' : 24, borderRadius: 12,
              transform: isStart || isDest ? 'translateX(-50%)' : 'translateX(-12px)',
              background: isStart ? theme.signalGreen : isDest ? theme.accent : cleared ? theme.signalGreen : current ? theme.accent : theme.cardBg,
              border: `3px solid ${isStart ? theme.signalGreen : isDest ? theme.accent : cleared ? theme.signalGreen : current ? theme.accent : theme.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: isStart || isDest ? 8 : 9, fontWeight: 700,
              color: cleared || current || isStart || isDest ? '#fff' : theme.textMuted,
              boxShadow: current ? `0 0 12px ${theme.accent}` : 'none',
              transition: 'all 0.3s ease',
            }}>
              {isStart ? 'START' : isDest ? 'DEST' : i + 1}
            </div>
          );
        })}
        {/* EV dot */}
        <div style={{
          position: 'absolute', left: `${Math.min(progressPct, 100)}%`, top: 12,
          width: 16, height: 16, borderRadius: '50%', transform: 'translateX(-8px)',
          background: theme.accent, border: '2px solid #fff',
          boxShadow: `0 0 10px ${theme.accent}`,
          transition: 'left 0.5s ease',
          zIndex: 2,
        }} />
      </div>
      {/* Labels */}
      <div style={{ position: 'relative', height: 20 }}>
        {pcts.map((pct, i) => (
          <span key={i} style={{
            position: 'absolute', left: `${pct}%`, transform: 'translateX(-50%)',
            fontSize: 9, color: theme.textMuted, whiteSpace: 'nowrap',
          }}>
            {intersectionNames[i]?.replace('INT_', 'I')}
          </span>
        ))}
      </div>
    </div>
  );
};
