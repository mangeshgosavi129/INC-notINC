import React, { useEffect, useState } from 'react';
import { theme } from '@inc/shared-ui';

interface Props {
  simId: string;
}

export const BaselineComparison: React.FC<Props> = ({ simId }) => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const BASE = import.meta.env.VITE_API_URL ?? '';
    fetch(`${BASE}/api/driver/arrival-comparison/${simId}`)
      .then(r => r.json())
      .then(d => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [simId]);

  if (loading) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: theme.textMuted }}>
        Computing fixed baseline comparison...
      </div>
    );
  }

  if (!data || data.detail) return null;

  return (
    <div style={{ paddingTop: 24 }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: theme.textPrimary, marginBottom: 12 }}>
        Performance vs Baseline
      </div>
      <div style={{
        background: theme.cardBg, padding: 16, borderRadius: 8, border: `1px solid ${theme.border}`,
        display: 'flex', flexDirection: 'column', gap: 12
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: theme.textSecondary, fontSize: 13 }}>EV Delay Saved</span>
          <span style={{ fontSize: 18, color: data.ev_delay_improvement_pct > 0 ? theme.signalGreen : theme.signalRed, fontWeight: 700 }}>
            {data.ev_delay_improvement_pct > 0 ? '+' : ''}{data.ev_delay_improvement_pct}%
          </span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ color: theme.textSecondary, fontSize: 13 }}>Queue Impact</span>
          <span style={{ fontSize: 14, color: data.queue_improvement_pct > 0 ? theme.signalGreen : theme.signalRed, fontWeight: 600 }}>
            {data.queue_improvement_pct > 0 ? '+' : ''}{data.queue_improvement_pct}%
          </span>
        </div>
        <div style={{ fontSize: 11, color: theme.textMuted, marginTop: 8, fontFamily: theme.fontMono }}>
          Agent Delay: {data.agent_ev_delay.toFixed(1)}s <br/>
          Baseline: {data.baseline_ev_delay.toFixed(1)}s
        </div>
      </div>
    </div>
  );
};
