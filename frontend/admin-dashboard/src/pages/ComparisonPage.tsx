import React, { useState, useEffect } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
  LineChart, Line,
} from 'recharts';
import { theme } from '@inc/shared-ui';
import {
  listSimulations, compareBaseline, getMetrics, initSimulation, runSimulation, dispatchEV, getState,
} from '../api/client';
import type { SimRun, ComparisonResult, MetricsSnapshot } from '../types';

export const ComparisonPage: React.FC = () => {
  const [runs, setRuns] = useState<SimRun[]>([]);
  const [mctsRunId, setMctsRunId] = useState('');
  const [baselineRunId, setBaselineRunId] = useState('');
  const [comparison, setComparison] = useState<ComparisonResult | null>(null);
  const [mctsMetrics, setMctsMetrics] = useState<MetricsSnapshot[]>([]);
  const [baselineMetrics, setBaselineMetrics] = useState<MetricsSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [progressMsg, setProgressMsg] = useState('');
  const [progressPct, setProgressPct] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listSimulations().then(setRuns).catch(() => {});
  }, []);

  const handleCompare = async () => {
    if (!mctsRunId || !baselineRunId) return;
    setLoading(true);
    setError(null);
    try {
      const [comp, mMet, bMet] = await Promise.all([
        compareBaseline(mctsRunId, baselineRunId),
        getMetrics(mctsRunId),
        getMetrics(baselineRunId),
      ]);
      setComparison(comp);
      setMctsMetrics(mMet);
      setBaselineMetrics(bMet);
    } catch (e: any) {
      setError(e.message);
    }
    setLoading(false);
  };

  const handleAutoRun = async () => {
    setLoading(true);
    setError(null);
    setProgressMsg('Initializing MCTS...');
    setProgressPct(0);
    try {
      const seed = Math.floor(Math.random() * 10000);
      const params = { duration_s: 180, sim_speed: 10, random_seed: seed, start_time_of_day: '08:00' };

      const mRes = await initSimulation({ ...params, controller_type: 'mcts', name: 'Auto MCTS' });
      await dispatchEV(mRes.run_id);
      
      setProgressMsg('Running MCTS Simulation...');
      let mDone = false;
      const mProm = runSimulation(mRes.run_id).then(() => { mDone = true; });
      while (!mDone) {
        try {
          const s = await getState(mRes.run_id);
          setProgressPct(Math.max(0, Math.min(100, (s.sim_time / params.duration_s) * 100)));
        } catch(e) {}
        await new Promise(r => setTimeout(r, 500));
      }
      await mProm;

      setProgressMsg('Initializing Baseline...');
      setProgressPct(0);

      const bRes = await initSimulation({ ...params, controller_type: 'fixed_time', name: 'Auto Baseline' });
      await dispatchEV(bRes.run_id);
      
      setProgressMsg('Running Baseline Simulation...');
      let bDone = false;
      const bProm = runSimulation(bRes.run_id).then(() => { bDone = true; });
      while (!bDone) {
        try {
          const s = await getState(bRes.run_id);
          setProgressPct(Math.max(0, Math.min(100, (s.sim_time / params.duration_s) * 100)));
        } catch(e) {}
        await new Promise(r => setTimeout(r, 500));
      }
      await bProm;

      setProgressMsg('Fetching Results...');
      setProgressPct(100);

      setMctsRunId(mRes.run_id);
      setBaselineRunId(bRes.run_id);

      const updatedRuns = await listSimulations();
      setRuns(updatedRuns);

      const [comp, mMet, bMet] = await Promise.all([
        compareBaseline(mRes.run_id, bRes.run_id),
        getMetrics(mRes.run_id),
        getMetrics(bRes.run_id),
      ]);
      setComparison(comp);
      setMctsMetrics(mMet);
      setBaselineMetrics(bMet);
      setProgressMsg('');
    } catch (e: any) {
      setError(e.message);
      setProgressMsg('');
    }
    setLoading(false);
  };

  const barData = comparison ? [
    { name: 'EV Delay (s)', MCTS: comparison.mcts_ev_delay, Baseline: comparison.baseline_ev_delay },
    { name: 'Avg Queue', MCTS: comparison.mcts_avg_queue, Baseline: comparison.baseline_avg_queue },
    { name: 'Throughput', MCTS: comparison.mcts_throughput, Baseline: comparison.baseline_throughput },
  ] : [];

  // Merge queue histories for overlay
  const overlayData = mctsMetrics.map((m, i) => ({
    sim_time: m.sim_time,
    mcts_queue: m.total_queue_length,
    baseline_queue: baselineMetrics[i]?.total_queue_length ?? 0,
  }));

  return (
    <div style={{ padding: 24, maxWidth: 1000, margin: '0 auto' }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16, color: theme.textPrimary }}>
        MCTS vs Baseline Comparison
      </h1>

      {/* Controls */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={mctsRunId} onChange={(e) => setMctsRunId(e.target.value)} style={selectStyle}>
          <option value="">Select MCTS run...</option>
          {runs.filter((r) => r.controller_type === 'mcts').map((r) => (
            <option key={r.run_id} value={r.run_id}>{r.name || r.run_id.slice(0, 12)} (MCTS)</option>
          ))}
        </select>
        <span style={{ color: theme.textMuted }}>vs</span>
        <select value={baselineRunId} onChange={(e) => setBaselineRunId(e.target.value)} style={selectStyle}>
          <option value="">Select baseline run...</option>
          {runs.filter((r) => r.controller_type === 'fixed_time').map((r) => (
            <option key={r.run_id} value={r.run_id}>{r.name || r.run_id.slice(0, 12)} (Fixed)</option>
          ))}
        </select>
        <button onClick={handleCompare} disabled={loading || !mctsRunId || !baselineRunId} style={btnStyle(theme.accent)}>
          Compare
        </button>
        <button onClick={handleAutoRun} disabled={loading} style={btnStyle(theme.signalGreen)}>
          {loading ? 'Running...' : 'Auto Run & Compare'}
        </button>
      </div>

      {error && <div style={{ color: theme.signalRed, fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {/* Progress Bar */}
      {loading && progressMsg && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 13, color: theme.textSecondary, marginBottom: 6 }}>{progressMsg} ({Math.round(progressPct)}%)</div>
          <div style={{ width: '100%', height: 8, background: theme.border, borderRadius: 4, overflow: 'hidden' }}>
            <div style={{ 
              width: `${progressPct}%`, 
              height: '100%', 
              background: theme.signalGreen, 
              transition: 'width 0.3s ease' 
            }} />
          </div>
        </div>
      )}

      {/* Results */}
      {comparison && (
        <>
          {/* Summary cards */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
            {[
              { label: 'EV Delay Improvement', value: comparison.ev_delay_improvement_pct },
              { label: 'Queue Improvement', value: comparison.queue_improvement_pct },
              { label: 'Throughput Improvement', value: comparison.throughput_improvement_pct },
            ].map((item) => (
              <div key={item.label} style={{
                flex: 1, minWidth: 180, background: theme.cardBg, borderRadius: 8,
                border: `1px solid ${theme.border}`, padding: 16, textAlign: 'center',
              }}>
                <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 4 }}>{item.label}</div>
                <div style={{
                  fontSize: 28, fontWeight: 700, fontFamily: theme.fontMono,
                  color: item.value > 0 ? theme.signalGreen : item.value < 0 ? theme.signalRed : theme.textPrimary,
                }}>
                  {item.value > 0 ? '+' : ''}{item.value.toFixed(1)}%
                </div>
              </div>
            ))}
          </div>

          {/* Bar chart */}
          <div style={{ background: theme.cardBg, borderRadius: 8, border: `1px solid ${theme.border}`, padding: 16, marginBottom: 16 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: theme.textSecondary, marginBottom: 12 }}>
              Side-by-Side Comparison
            </div>
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={barData}>
                <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                <XAxis dataKey="name" stroke={theme.textMuted} fontSize={11} />
                <YAxis stroke={theme.textMuted} fontSize={10} />
                <Tooltip contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 12 }} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="MCTS" fill={theme.accent} radius={[4, 4, 0, 0]} />
                <Bar dataKey="Baseline" fill={theme.textMuted} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Queue overlay */}
          {overlayData.length > 0 && (
            <div style={{ background: theme.cardBg, borderRadius: 8, border: `1px solid ${theme.border}`, padding: 16 }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: theme.textSecondary, marginBottom: 12 }}>
                Queue Evolution Overlay
              </div>
              <ResponsiveContainer width="100%" height={220}>
                <LineChart data={overlayData}>
                  <CartesianGrid strokeDasharray="3 3" stroke={theme.border} />
                  <XAxis dataKey="sim_time" tickFormatter={(v: number) => `${Math.floor(v)}s`} stroke={theme.textMuted} fontSize={10} />
                  <YAxis stroke={theme.textMuted} fontSize={10} />
                  <Tooltip contentStyle={{ background: theme.cardBg, border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 12 }} />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="mcts_queue" name="MCTS Queue" stroke={theme.accent} dot={false} strokeWidth={2} />
                  <Line type="monotone" dataKey="baseline_queue" name="Baseline Queue" stroke={theme.textMuted} dot={false} strokeWidth={2} strokeDasharray="5 5" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </div>
  );
};

const selectStyle: React.CSSProperties = {
  padding: '6px 12px', borderRadius: 6, border: `1px solid ${theme.border}`,
  background: theme.cardBg, color: theme.textPrimary, fontSize: 13, minWidth: 200,
};

const btnStyle = (bg: string): React.CSSProperties => ({
  padding: '6px 16px', border: 'none', borderRadius: 6,
  background: bg, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
});
