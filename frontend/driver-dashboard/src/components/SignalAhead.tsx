import React from 'react';
import { SignalIcon, theme } from '@inc/shared-ui';

interface Props {
  signalState: string | null;
  intersection: string | null;
  timeToGreen: number | null;
}

export const SignalAhead: React.FC<Props> = ({ signalState, intersection, timeToGreen }) => {
  const state = (signalState as 'GREEN' | 'AMBER' | 'ALL_RED') ?? 'ALL_RED';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      gap: 20, padding: '16px 20px',
      background: theme.cardBg, borderRadius: 12, border: `1px solid ${theme.border}`,
    }}>
      <SignalIcon state={state} size={80} />
      <div>
        <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary }}>
          {intersection ?? 'No signal ahead'}
        </div>
        <div style={{ fontSize: 13, color: theme.textSecondary, marginTop: 4 }}>
          {signalState ?? '--'}
        </div>
        {timeToGreen !== null && signalState !== 'GREEN' && (
          <div style={{
            fontSize: 22, fontWeight: 700, fontFamily: theme.fontMono,
            color: theme.signalAmber, marginTop: 4,
          }}>
            {timeToGreen.toFixed(0)}s to green
          </div>
        )}
      </div>
    </div>
  );
};
