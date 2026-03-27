import React from 'react';
import { theme } from './theme';

interface QueueBarProps {
  queue: number;
  maxQueue?: number;
  height?: number;
  width?: number;
  showLabel?: boolean;
}

export const QueueBar: React.FC<QueueBarProps> = ({
  queue,
  maxQueue = 60,
  height = 8,
  width = 80,
  showLabel = false,
}) => {
  const pct = Math.min(queue / maxQueue, 1);
  const color = pct < 0.4
    ? theme.signalGreen
    : pct < 0.7
      ? theme.signalAmber
      : theme.signalRed;

  return (
    <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
      <div
        style={{
          width,
          height,
          background: theme.border,
          borderRadius: height / 2,
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct * 100}%`,
            height: '100%',
            background: color,
            borderRadius: height / 2,
            transition: 'width 0.3s ease, background 0.3s ease',
          }}
        />
      </div>
      {showLabel && (
        <span style={{ fontSize: 11, color: theme.textSecondary, minWidth: 24 }}>
          {Math.round(queue)}
        </span>
      )}
    </div>
  );
};
