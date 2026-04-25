import React from 'react';
import { useSimContext } from '../context/SimulationContext';
import { SimControls } from '../components/SimControls';
import { AlertBanner } from '../components/AlertBanner';
import { VizSwitch } from '../components/VizSwitch';
import { MetricsPanel } from '../components/MetricsPanel';
import { EVTracker } from '../components/EVTracker';
import { AgentDecisionLog } from '../components/AgentDecisionLog';
import { QueueChart } from '../components/QueueChart';
import { EventPanel } from '../components/EventPanel';
import { SignalIndicator } from '../components/SignalIndicator';
import { removeBlockage } from '../api/client';
import { theme } from '@inc/shared-ui';

export const SimulationPage: React.FC = () => {
  const { state, metricsHistory, decisions, alerts, runId, simStatus } = useSimContext();

  const handleUnblock = async (from: string, to: string) => {
    if (runId) {
      try { await removeBlockage(runId, from, to); } catch { /* ignore */ }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <AlertBanner alerts={alerts} />
      <SimControls />

      {/* Welcome screen when no simulation is running */}
      {simStatus === 'idle' && (
        <div style={{
          flex: 1, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center', gap: 16, padding: 40,
        }}>
          <div style={{ fontSize: 32, fontWeight: 800, color: theme.textPrimary }}>
            Corridor Control Room
          </div>
          <div style={{ fontSize: 14, color: theme.textSecondary, textAlign: 'center', maxWidth: 500, lineHeight: 1.8 }}>
            Simulate traffic signal optimization for emergency vehicle corridor clearance
            using a placeholder AI-agent controller.
          </div>
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12,
            background: theme.cardBg, padding: 20, borderRadius: 12, border: `1px solid ${theme.border}`,
            fontSize: 13, color: theme.textSecondary, lineHeight: 1.8,
          }}>
            <div><span style={{ color: theme.signalGreen, fontWeight: 700 }}>1.</span> Choose <b style={{ color: theme.textPrimary }}>Agent</b> (placeholder) or <b style={{ color: theme.textPrimary }}>Fixed Time</b> controller</div>
            <div><span style={{ color: theme.signalGreen, fontWeight: 700 }}>2.</span> Click <b style={{ color: theme.signalGreen }}>Start Simulation</b> to begin</div>
            <div><span style={{ color: theme.signalGreen, fontWeight: 700 }}>3.</span> Click <b style={{ color: theme.accent }}>Dispatch Ambulance</b> to send an EV through the corridor</div>
            <div><span style={{ color: theme.signalGreen, fontWeight: 700 }}>4.</span> Watch placeholder agent decisions while routing is implemented</div>
          </div>
        </div>
      )}

      {/* Main simulation view */}
      {simStatus !== 'idle' && (
        <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '1fr 380px', gap: 0, overflow: 'hidden' }}>
          {/* Left: Visualization + Chart */}
          <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 16, gap: 12 }}>
            {/* Signal strip */}
            {state && state.intersections.length > 0 && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {state.intersections.map((ix) => (
                  <SignalIndicator key={ix.intersection_id} intersection={ix} compact />
                ))}
              </div>
            )}

            {/* Corridor viz */}
            <div style={{
              flex: 1, minHeight: 200, background: theme.cardBg,
              borderRadius: 8, border: `1px solid ${theme.border}`, padding: 12,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              {state && state.intersections.length > 0 ? (
                <VizSwitch intersections={state.intersections} ev={state.ev} />
              ) : (
                <div style={{ color: theme.textMuted, fontSize: 14 }}>
                  Waiting for simulation data...
                </div>
              )}
            </div>

            {/* Queue chart */}
            <div style={{
              background: theme.cardBg, borderRadius: 8,
              border: `1px solid ${theme.border}`, padding: 12,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, marginBottom: 8 }}>
                Queue Evolution
              </div>
              <QueueChart data={metricsHistory} />
            </div>
          </div>

          {/* Right: Metrics + EV + Agent + Events */}
          <div style={{
            display: 'flex', flexDirection: 'column', gap: 8, padding: '16px 16px 16px 0',
            overflow: 'auto',
          }}>
            <MetricsPanel current={state?.metrics ?? null} history={metricsHistory} />

            <div style={{
              background: theme.cardBg, borderRadius: 8,
              border: `1px solid ${theme.border}`,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, padding: '10px 12px 0' }}>
                EV Tracker
              </div>
              <EVTracker ev={state?.ev ?? null} />
            </div>

            <div style={{
              background: theme.cardBg, borderRadius: 8, flex: 1, minHeight: 0,
              border: `1px solid ${theme.border}`, overflow: 'hidden',
              display: 'flex', flexDirection: 'column',
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: theme.textSecondary, padding: '10px 12px 4px' }}>
                Agent Decisions
              </div>
              <div style={{ flex: 1, overflow: 'auto' }}>
                <AgentDecisionLog decisions={decisions} />
              </div>
            </div>

            <div style={{
              background: theme.cardBg, borderRadius: 8,
              border: `1px solid ${theme.border}`,
            }}>
              <EventPanel alerts={alerts} onUnblock={handleUnblock} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
