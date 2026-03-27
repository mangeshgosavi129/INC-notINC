import React, { useEffect, useState } from 'react';
import { theme } from '@inc/shared-ui';
import type { EVJourneySummary } from '../types';

interface Props {
  simId: string;
}

export const JourneyStats: React.FC<Props> = ({ simId }) => {
  const [summary, setSummary] = useState<EVJourneySummary | null>(null);

  useEffect(() => {
    const BASE = import.meta.env.VITE_API_URL ?? '';
    fetch(`${BASE}/api/analytics/ev-journey/${simId}`)
      .then((r) => r.json())
      .then(setSummary)
      .catch(() => {});
  }, [simId]);

  if (!summary) {
    return (
      <div style={{ padding: 24, textAlign: 'center', color: theme.textMuted }}>
        Loading journey summary...
      </div>
    );
  }

  const stats = [
    { label: 'Total Time', value: `${summary.actual_time_s?.toFixed(1) ?? '--'}s`, color: theme.textPrimary },
    { label: 'Free Flow Time', value: `${summary.free_flow_time_s?.toFixed(1) ?? '--'}s`, color: theme.textSecondary },
    { label: 'Signal Delay', value: `${summary.total_signal_delay_s?.toFixed(1) ?? '--'}s`, color: theme.signalRed },
    { label: 'Intersections Cleared', value: String(summary.intersections_cleared ?? 0), color: theme.signalGreen },
    { label: 'Intersections Waited', value: String(summary.intersections_waited ?? 0), color: theme.signalAmber },
  ];

  return (
    <div style={{ padding: 24 }}>
      <div style={{
        textAlign: 'center', fontSize: 24, fontWeight: 800,
        color: theme.signalGreen, marginBottom: 20,
      }}>
        ARRIVED AT DESTINATION
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {stats.map((s) => (
          <div key={s.label} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '10px 16px', background: theme.cardBg,
            borderRadius: 8, border: `1px solid ${theme.border}`,
          }}>
            <span style={{ fontSize: 13, color: theme.textSecondary }}>{s.label}</span>
            <span style={{ fontSize: 18, fontWeight: 700, fontFamily: theme.fontMono, color: s.color }}>
              {s.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
