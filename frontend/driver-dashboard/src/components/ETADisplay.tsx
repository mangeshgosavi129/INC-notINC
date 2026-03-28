import React from 'react';
import { theme } from '@inc/shared-ui';

interface Props {
  etaS: number | null;
  freeFlowEtaS: number | null;
  progressPct: number;
}

function formatEta(s: number | null): string {
  if (s === null || s <= 0) return '--:--';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}

export const ETADisplay: React.FC<Props> = ({ etaS, freeFlowEtaS, progressPct }) => {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-around',
      padding: '16px 20px', background: theme.cardBg,
      borderRadius: 12, border: `1px solid ${theme.border}`,
    }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>
          ETA
        </div>
        <div style={{
          fontSize: 36, fontWeight: 800, fontFamily: theme.fontMono,
          color: theme.textPrimary,
        }}>
          {formatEta(etaS)}
        </div>
      </div>

      <div style={{ width: 1, height: 50, background: theme.border }} />

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>
          Free Flow
        </div>
        <div style={{
          fontSize: 20, fontWeight: 600, fontFamily: theme.fontMono,
          color: theme.textSecondary,
        }}>
          {formatEta(freeFlowEtaS)}
        </div>
      </div>

      <div style={{ width: 1, height: 50, background: theme.border }} />

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 10, color: theme.textMuted, textTransform: 'uppercase', marginBottom: 4 }}>
          Progress
        </div>
        <div style={{
          fontSize: 24, fontWeight: 700, fontFamily: theme.fontMono,
          color: theme.accent,
        }}>
          {progressPct.toFixed(0)}%
        </div>
      </div>
    </div>
  );
};
