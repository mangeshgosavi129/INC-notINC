import React, { useRef, useEffect } from 'react';
import { theme } from '@inc/shared-ui';
import type { AgentDecision } from '../types';

interface Props {
  decisions: AgentDecision[];
}

function summarizeActions(actions: Record<string, { action_type: string; target_phase?: number }>): string {
  return Object.entries(actions)
    .map(([iid, a]) => {
      const short = iid.replace('INT_', 'I');
      const tp = a.target_phase !== undefined ? `(${a.target_phase})` : '';
      return `${short}:${a.action_type}${tp}`;
    })
    .join(', ');
}

export const AgentDecisionLog: React.FC<Props> = ({ decisions }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [decisions.length]);

  if (decisions.length === 0) {
    return (
      <div style={{ padding: 12, color: theme.textMuted, fontSize: 13, textAlign: 'center' }}>
        No agent decisions yet
      </div>
    );
  }

  return (
    <div style={{ overflowY: 'auto', maxHeight: 250, fontSize: 11 }}>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ position: 'sticky', top: 0, background: theme.cardBg, zIndex: 1 }}>
            {['Time', 'Status', 'ms', 'Actions'].map((h) => (
              <th key={h} style={{
                padding: '4px 6px', textAlign: 'left', borderBottom: `1px solid ${theme.border}`,
                color: theme.textSecondary, fontWeight: 600, fontSize: 10,
              }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {decisions.map((d, i) => (
            <tr key={d.decision_id ?? i} style={{ borderBottom: `1px solid ${theme.border}05` }}>
              <td style={cellStyle}>{d.sim_time.toFixed(1)}s</td>
              <td style={cellStyle}>{d.status ?? 'not_implemented'}</td>
              <td style={cellStyle}>{d.computation_ms?.toFixed(0) ?? '-'}</td>
              <td style={{ ...cellStyle, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {summarizeActions(d.actions)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div ref={endRef} />
    </div>
  );
};

const cellStyle: React.CSSProperties = {
  padding: '3px 6px', color: theme.textPrimary,
};
