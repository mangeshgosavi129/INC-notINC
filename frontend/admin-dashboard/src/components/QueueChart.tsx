import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { theme } from '@inc/shared-ui';
import type { MetricsSnapshot } from '../types';

interface Props {
  data: MetricsSnapshot[];
}

export const QueueChart: React.FC<Props> = ({ data }) => {
  if (data.length === 0) {
    return (
      <div style={{ padding: 20, color: theme.textMuted, fontSize: 13, textAlign: 'center' }}>
        No metrics data yet. Start a simulation to see queue charts.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
        <XAxis
          dataKey="sim_time"
          tickFormatter={(v: number) => `${Math.floor(v)}s`}
          stroke={theme.textMuted}
          fontSize={10}
        />
        <YAxis stroke={theme.textMuted} fontSize={10} />
        <Tooltip
          contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 12 }}
          labelStyle={{ color: theme.textPrimary }}
          labelFormatter={(v: number) => `t = ${v.toFixed(1)}s`}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Line type="monotone" dataKey="total_queue_length" name="Total Queue"
          stroke={theme.accent} dot={false} strokeWidth={2} />
        <Line type="monotone" dataKey="max_queue_length" name="Max Queue"
          stroke={theme.signalRed} dot={false} strokeWidth={1.5} />
        <Line type="monotone" dataKey="avg_queue_length" name="Avg Queue"
          stroke={theme.signalAmber} dot={false} strokeWidth={1.5} />
      </LineChart>
    </ResponsiveContainer>
  );
};
