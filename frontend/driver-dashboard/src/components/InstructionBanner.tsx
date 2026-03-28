import React from 'react';
import { theme } from '@inc/shared-ui';

interface Props {
  instruction: 'PROCEED' | 'STOP' | 'SLOW_DOWN' | 'STANDBY';
  intersection?: string | null;
  startNode?: string | null;
  destinationNode?: string | null;
}

const config: Record<string, { bg: string; text: string; sub: string }> = {
  PROCEED: { bg: theme.signalGreen, text: 'PROCEED', sub: 'Signal cleared ahead' },
  STOP: { bg: theme.signalRed, text: 'STOP', sub: 'Red signal — hold position' },
  SLOW_DOWN: { bg: theme.signalAmber, text: 'SLOW DOWN', sub: 'Signal changing ahead' },
  STANDBY: { bg: theme.textMuted, text: 'STANDBY', sub: 'Awaiting dispatch' },
};

export const InstructionBanner: React.FC<Props> = ({ instruction, intersection, startNode, destinationNode }) => {
  const c = config[instruction] ?? config.STANDBY;

  return (
    <div style={{
      background: c.bg, padding: '20px 24px', textAlign: 'center',
      transition: 'background 0.3s ease',
    }}>
      <div style={{ fontSize: 36, fontWeight: 800, color: '#fff', letterSpacing: 2 }}>
        {c.text}
      </div>
      <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.9)', marginTop: 8, fontWeight: 600 }}>
        {startNode && destinationNode && <div>From {startNode} → To {destinationNode}</div>}
      </div>
      <div style={{ fontSize: 14, color: 'rgba(255,255,255,0.8)', marginTop: 4 }}>
        {intersection ? `Next: ${intersection} — ${c.sub}` : c.sub}
      </div>
    </div>
  );
};
