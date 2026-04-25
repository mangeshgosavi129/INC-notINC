import React, { useState, useEffect } from 'react';
import { theme } from '@inc/shared-ui';
import { listSimulations, exportRun } from '../api/client';
import { useSimContext } from '../context/SimulationContext';
import type { SimRun } from '../types';

export const HistoryPage: React.FC = () => {
  const [runs, setRuns] = useState<SimRun[]>([]);
  const { loadRun } = useSimContext();

  useEffect(() => {
    listSimulations().then(setRuns).catch(() => {});
  }, []);

  const handleExport = async (runId: string) => {
    try {
      const data = await exportRun(runId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${runId}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch { /* ignore */ }
  };

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16, color: theme.textPrimary }}>
        Simulation History
      </h1>

      {runs.length === 0 ? (
        <div style={{ color: theme.textMuted, fontSize: 14, padding: 20, textAlign: 'center' }}>
          No simulation runs yet
        </div>
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {['Name', 'Controller', 'Status', 'Sim Time', 'Actions'].map((h) => (
                <th key={h} style={{
                  padding: '8px 12px', textAlign: 'left',
                  borderBottom: `2px solid ${theme.border}`,
                  color: theme.textSecondary, fontSize: 12, fontWeight: 600,
                }}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id} style={{ borderBottom: `1px solid ${theme.border}` }}>
                <td style={cellStyle}>
                  <span style={{ fontWeight: 600 }}>{run.name || 'Unnamed'}</span>
                  <div style={{ fontSize: 10, color: theme.textMuted, fontFamily: theme.fontMono }}>
                    {run.run_id.slice(0, 16)}
                  </div>
                </td>
                <td style={cellStyle}>
                  <span style={{
                    fontSize: 11, padding: '2px 8px', borderRadius: 4,
                    background: run.controller_type === 'agent' ? theme.accent + '20' : theme.border,
                    color: run.controller_type === 'agent' ? theme.accent : theme.textSecondary,
                  }}>
                    {run.controller_type.toUpperCase()}
                  </span>
                </td>
                <td style={cellStyle}>
                  <span style={{ fontSize: 12, color: theme.textSecondary }}>{run.status}</span>
                </td>
                <td style={{ ...cellStyle, fontFamily: theme.fontMono, fontSize: 12 }}>
                  {run.sim_time?.toFixed(1) ?? '--'}s
                </td>
                <td style={cellStyle}>
                  <button onClick={() => loadRun(run.run_id)} style={smallBtn(theme.accent)}>View</button>
                  <button onClick={() => handleExport(run.run_id)} style={{ ...smallBtn(theme.border), marginLeft: 4 }}>
                    Export
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

const cellStyle: React.CSSProperties = {
  padding: '10px 12px', color: theme.textPrimary, fontSize: 13,
};

const smallBtn = (bg: string): React.CSSProperties => ({
  padding: '3px 10px', border: 'none', borderRadius: 4,
  background: bg, color: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer',
});
