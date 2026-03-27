import React from 'react';
import { theme } from './theme';

interface SignalIconProps {
  state: 'GREEN' | 'AMBER' | 'ALL_RED' | 'RED';
  size?: number;
}

const dimColor = '#1e293b';

export const SignalIcon: React.FC<SignalIconProps> = ({ state, size = 32 }) => {
  const r = size * 0.22;
  const cx = size / 2;
  const gap = size * 0.3;
  const topY = size * 0.2;

  const colors = {
    red: state === 'ALL_RED' || state === 'RED' ? theme.signalRed : dimColor,
    amber: state === 'AMBER' ? theme.signalAmber : dimColor,
    green: state === 'GREEN' ? theme.signalGreen : dimColor,
  };

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <rect
        x={cx - size * 0.25}
        y={2}
        width={size * 0.5}
        height={size - 4}
        rx={size * 0.1}
        fill="#0f172a"
        stroke="#334155"
        strokeWidth={1}
      />
      <circle cx={cx} cy={topY} r={r} fill={colors.red} />
      <circle cx={cx} cy={topY + gap} r={r} fill={colors.amber} />
      <circle cx={cx} cy={topY + gap * 2} r={r} fill={colors.green} />
      {state === 'GREEN' && (
        <circle cx={cx} cy={topY + gap * 2} r={r + 3} fill="none" stroke={theme.signalGreen} strokeWidth={1.5} opacity={0.5} />
      )}
      {(state === 'ALL_RED' || state === 'RED') && (
        <circle cx={cx} cy={topY} r={r + 3} fill="none" stroke={theme.signalRed} strokeWidth={1.5} opacity={0.5} />
      )}
    </svg>
  );
};
