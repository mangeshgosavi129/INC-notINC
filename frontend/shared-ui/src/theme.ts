export const theme = {
  bg: '#0a0e1a',
  cardBg: '#111827',
  cardBgHover: '#1a2332',
  border: '#1e293b',
  borderLight: '#334155',
  accent: '#3b82f6',
  accentHover: '#2563eb',
  textPrimary: '#f1f5f9',
  textSecondary: '#94a3b8',
  textMuted: '#64748b',
  signalRed: '#ef4444',
  signalAmber: '#f59e0b',
  signalGreen: '#22c55e',
  success: '#22c55e',
  warning: '#f59e0b',
  danger: '#ef4444',
  fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  fontMono: "'JetBrains Mono', 'Fira Code', monospace",
  radius: '8px',
  radiusSm: '4px',
  radiusLg: '12px',
  shadow: '0 4px 6px -1px rgba(0, 0, 0, 0.3)',
  shadowLg: '0 10px 15px -3px rgba(0, 0, 0, 0.4)',
} as const;

export type Theme = typeof theme;

export const signalColor = (state: string): string => {
  switch (state) {
    case 'GREEN': return theme.signalGreen;
    case 'AMBER': return theme.signalAmber;
    case 'ALL_RED':
    case 'RED':
    default: return theme.signalRed;
  }
};
