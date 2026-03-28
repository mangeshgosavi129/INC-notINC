import React from 'react';
import { theme } from '@inc/shared-ui';
import type { MetricsSnapshot } from '../types';

interface Props {
  current: MetricsSnapshot | null;
  history: MetricsSnapshot[];
}

interface KPICardProps {
  label: string;
  value: string;
  color: string;
  sparkData: number[];
}

const Sparkline: React.FC<{ data: number[]; color: string }> = ({ data, color }) => {
  if (data.length < 2) return null;
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const w = 60;
  const h = 20;
  const points = data.map((v, i) =>
    `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`
  ).join(' ');

  return (
    <svg width={w} height={h} style={{ opacity: 0.7 }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
};

const KPICard: React.FC<KPICardProps> = ({ label, value, color, sparkData }) => (
  <div style={{
    background: theme.cardBg, border: `1px solid ${theme.border}`, borderRadius: 8,
    padding: '10px 14px', flex: 1, minWidth: 120,
  }}>
    <div style={{ fontSize: 10, color: theme.textMuted, marginBottom: 4, textTransform: 'uppercase', letterSpacing: 0.5 }}>
      {label}
    </div>
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
      <span style={{ fontSize: 22, fontWeight: 700, color, fontFamily: theme.fontMono }}>
        {value}
      </span>
      <Sparkline data={sparkData} color={color} />
    </div>
  </div>
);

export const MetricsPanel: React.FC<Props> = ({ current, history }) => {
  const recent = history.slice(-20);

  const hasData = current && current.total_queue_length !== undefined;

  const cards = [
    {
      label: 'Total Queue',
      value: hasData ? current.total_queue_length.toFixed(0) : '--',
      color: theme.signalAmber,
      sparkData: recent.map((m) => m.total_queue_length ?? 0),
    },
    {
      label: 'Max Queue',
      value: hasData ? current.max_queue_length.toFixed(0) : '--',
      color: theme.signalRed,
      sparkData: recent.map((m) => m.max_queue_length ?? 0),
    },
    {
      label: 'Throughput',
      value: hasData ? String(current.total_throughput ?? 0) : '--',
      color: theme.signalGreen,
      sparkData: recent.map((m) => m.total_throughput ?? 0),
    },
    {
      label: 'EV Progress',
      value: hasData ? `${(current.ev_progress_pct ?? 0).toFixed(0)}%` : '--',
      color: theme.accent,
      sparkData: recent.map((m) => m.ev_progress_pct ?? 0),
    },
  ];

  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {cards.map((c) => <KPICard key={c.label} {...c} />)}
    </div>
  );
};
