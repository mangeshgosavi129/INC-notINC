import React, { useState, useEffect } from 'react';
import { theme } from '@inc/shared-ui';
import { useDriverState } from './hooks/useDriverState';
import { InstructionBanner } from './components/InstructionBanner';
import { SignalAhead } from './components/SignalAhead';
import { RouteProgress } from './components/RouteProgress';
import { ETADisplay } from './components/ETADisplay';
import { CorridorStatus } from './components/CorridorStatus';
import { JourneyStats } from './components/JourneyStats';
import { DirectionsBanner } from './components/DirectionsBanner';

interface SimRun {
  run_id: string;
  name: string;
  controller_type: string;
  status: string;
}

const BASE = import.meta.env.VITE_API_URL ?? '';

function ConnectScreen({ onConnect }: { onConnect: (simId: string) => void }) {
  const [runs, setRuns] = useState<SimRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [manualId, setManualId] = useState('');

  useEffect(() => {
    const fetchRuns = () => {
      fetch(`${BASE}/api/simulation/list`)
        .then((r) => r.json())
        .then((data) => { setRuns(data); setLoading(false); })
        .catch(() => setLoading(false));
    };
    fetchRuns();
    const interval = setInterval(fetchRuns, 3000);
    return () => clearInterval(interval);
  }, []);

  const activeRuns = runs.filter((r) => r.status === 'running' || r.status === 'initialized');

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      justifyContent: 'center', height: '100vh', gap: 20, padding: 24,
    }}>
      <div style={{ fontSize: 24, fontWeight: 800, color: theme.textPrimary }}>
        EV Driver Dashboard
      </div>
      <div style={{ fontSize: 13, color: theme.textSecondary, textAlign: 'center' }}>
        Select a running simulation to connect
      </div>

      {loading ? (
        <div style={{ color: theme.textMuted, fontSize: 13 }}>Loading simulations...</div>
      ) : activeRuns.length > 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 360 }}>
          {activeRuns.map((run) => (
            <button
              key={run.run_id}
              onClick={() => onConnect(run.run_id)}
              style={{
                padding: '14px 16px', border: `1px solid ${theme.border}`, borderRadius: 8,
                background: theme.cardBg, color: theme.textPrimary, cursor: 'pointer',
                textAlign: 'left', fontSize: 13, display: 'flex', justifyContent: 'space-between',
                alignItems: 'center',
              }}
            >
              <div>
                <div style={{ fontWeight: 600 }}>{run.name || 'Unnamed Run'}</div>
                <div style={{ fontSize: 10, color: theme.textMuted, fontFamily: "'JetBrains Mono', monospace", marginTop: 2 }}>
                  {run.run_id.slice(0, 16)}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{
                  fontSize: 10, padding: '2px 6px', borderRadius: 4,
                  background: run.controller_type === 'agent' ? theme.accent + '20' : theme.border,
                  color: run.controller_type === 'agent' ? theme.accent : theme.textSecondary,
                }}>
                  {run.controller_type.toUpperCase()}
                </span>
                <span style={{
                  fontSize: 10, padding: '2px 6px', borderRadius: 4,
                  background: theme.signalGreen + '20', color: theme.signalGreen,
                }}>
                  {run.status.toUpperCase()}
                </span>
              </div>
            </button>
          ))}
        </div>
      ) : (
        <div style={{
          color: theme.textMuted, fontSize: 13, padding: 20, textAlign: 'center',
          background: theme.cardBg, borderRadius: 8, border: `1px solid ${theme.border}`,
          maxWidth: 360, width: '100%',
        }}>
          No active simulations found.<br />
          Start one from the Admin Dashboard first.
        </div>
      )}

      {/* Manual entry fallback */}
      <div style={{ display: 'flex', gap: 8, maxWidth: 360, width: '100%', marginTop: 8 }}>
        <input
          value={manualId}
          onChange={(e) => setManualId(e.target.value)}
          placeholder="Or paste a run ID..."
          style={{
            flex: 1, padding: '8px 12px', borderRadius: 6,
            border: `1px solid ${theme.border}`, background: theme.cardBg,
            color: theme.textPrimary, fontSize: 12, outline: 'none',
            fontFamily: "'JetBrains Mono', monospace",
          }}
        />
        <button
          onClick={() => manualId.trim() && onConnect(manualId.trim())}
          disabled={!manualId.trim()}
          style={{
            padding: '8px 16px', border: 'none', borderRadius: 6,
            background: manualId.trim() ? theme.accent : theme.border,
            color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
          }}
        >
          Connect
        </button>
      </div>
    </div>
  );
}

export default function App() {
  const urlParams = new URLSearchParams(window.location.search);
  const [simId, setSimId] = useState<string | null>(urlParams.get('sim_id'));
  const evId = urlParams.get('ev_id') ?? 'AMB_01';

  const handleConnect = (id: string) => {
    setSimId(id);
    const url = new URL(window.location.href);
    url.searchParams.set('sim_id', id);
    window.history.pushState({}, '', url.toString());
  };

  const handleSimLost = () => {
    // Simulation was reset/deleted — go back to connect screen
    setSimId(null);
    const url = new URL(window.location.href);
    url.searchParams.delete('sim_id');
    window.history.pushState({}, '', url.toString());
  };

  const { status, corridor, eta } = useDriverState(simId, evId, handleSimLost);

  if (!simId) {
    return <ConnectScreen onConnect={handleConnect} />;
  }

  const instruction = status?.instruction ?? 'STANDBY';
  const isArrived = status?.status === 'arrived';

  if (isArrived) {
    return (
      <div style={{ maxWidth: 480, margin: '0 auto', minHeight: '100vh', background: theme.bg }}>
        <InstructionBanner instruction="PROCEED" intersection={null} />
        <JourneyStats simId={simId} />
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 480, margin: '0 auto', minHeight: '100vh', background: theme.bg }}>
      <InstructionBanner
        instruction={instruction}
        intersection={status?.next_intersection}
        startNode={status?.start_node ?? null}
        destinationNode={status?.destination_node ?? null}
      />
      <DirectionsBanner directions={status?.directions ?? null} />

      <div style={{ padding: '12px 0' }}>
        <SignalAhead
          signalState={status?.next_signal_state ?? null}
          intersection={status?.next_intersection ?? null}
          timeToGreen={status?.time_to_green_s ?? null}
        />
      </div>

      <RouteProgress 
        progressPct={status?.progress_pct ?? 0}
        intersectionNames={corridor ? corridor.intersections.map(ix => ix.name) : undefined}
        startNode={status?.start_node ?? null}
        destinationNode={status?.destination_node ?? null}
      />

      <div style={{ padding: '0 12px 12px' }}>
        <ETADisplay
          etaS={eta?.eta_s ?? status?.eta_destination_s ?? null}
          freeFlowEtaS={eta?.free_flow_eta_s ?? null}
          progressPct={status?.progress_pct ?? 0}
        />
      </div>

      {corridor && (
        <CorridorStatus
          intersections={corridor.intersections}
          evLinkIndex={corridor.ev?.position_link_index ?? 0}
          evStatus={corridor.ev?.status ?? 'idle'}
          startNode={corridor.start_node ?? status?.start_node ?? null}
          destinationNode={corridor.destination_node ?? status?.destination_node ?? null}
        />
      )}

      {/* Connection status */}
      <div style={{
        position: 'fixed', bottom: 8, right: 8,
        fontSize: 10, color: theme.textMuted, padding: '2px 8px',
        background: theme.cardBg, borderRadius: 4,
      }}>
        {simId.slice(0, 12)} | {evId}
      </div>
    </div>
  );
}
