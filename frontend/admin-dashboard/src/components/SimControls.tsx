import React, { useState, useEffect } from 'react';
import { useSimContext } from '../context/SimulationContext';
import { getIntersections } from '../api/client';
import type { IntersectionConfig } from '../types';
import { theme } from '@inc/shared-ui';

const speeds = [1, 2, 5];

function formatTime(seconds: number, startOfDay = 28800): string {
  const total = startOfDay + seconds;
  const h = Math.floor(total / 3600) % 24;
  const m = Math.floor((total % 3600) / 60);
  const s = Math.floor(total % 60);
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export const SimControls: React.FC = () => {
  const {
    runId, simStatus, initSim, startSim, pauseSim, resumeSim, resetSim, changeSpeed, dispatchEV, error,
    state,
  } = useSimContext();

  const [speed, setSpeed] = useState(5);
  const [controllerType, setControllerType] = useState<'mcts' | 'fixed_time'>('mcts');
  const [evDispatched, setEvDispatched] = useState(false);
  const [intersectionConfigs, setIntersectionConfigs] = useState<IntersectionConfig[]>([]);
  const [startIntersection, setStartIntersection] = useState('');
  const [endIntersection, setEndIntersection] = useState('');

  useEffect(() => {
    getIntersections()
      .then((configs) => {
        setIntersectionConfigs(configs);
        if (configs.length >= 2) {
          setStartIntersection(configs[0].intersection_id);
          setEndIntersection(configs[configs.length - 1].intersection_id);
        }
      })
      .catch(() => {});
  }, []);

  const handleInit = async () => {
    setEvDispatched(false);
    const id = await initSim({ controller_type: controllerType, duration_s: 3600, sim_speed: speed });
    if (id) await startSim(id);
  };

  const handleSpeedChange = (s: number) => {
    setSpeed(s);
    changeSpeed(s);
  };

  const handleDispatchEV = () => {
    dispatchEV({
      ev_id: 'AMB_01',
      vehicle_type: 'ambulance',
      corridor_id: 'CORR_01',
      max_speed_kmph: 60,
      start_intersection: startIntersection || undefined,
      end_intersection: endIntersection || undefined,
    });
    setEvDispatched(true);
  };

  const handleReset = () => {
    setEvDispatched(false);
    resetSim();
  };

  const evStatus = state?.ev?.status;
  const evActive = evStatus && evStatus !== 'idle' && evStatus !== 'arrived';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 16px',
      background: theme.cardBg, borderBottom: `1px solid ${theme.border}`,
      flexWrap: 'wrap',
    }}>
      {/* Sim clock */}
      <div style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 22, fontWeight: 700,
        color: theme.accent, minWidth: 110,
        background: theme.bg, padding: '4px 12px', borderRadius: 6,
        border: `1px solid ${theme.border}`,
      }}>
        {state ? formatTime(state.sim_time) : '--:--:--'}
      </div>

      {/* Controller selector — only before starting */}
      {simStatus === 'idle' && (
        <select
          value={controllerType}
          onChange={(e) => setControllerType(e.target.value as 'mcts' | 'fixed_time')}
          style={selectStyle}
        >
          <option value="mcts">MCTS (Adaptive)</option>
          <option value="fixed_time">Fixed Time (Baseline)</option>
        </select>
      )}

      {/* Main action button */}
      {simStatus === 'idle' ? (
        <button onClick={handleInit} style={btnStyle(theme.signalGreen, true)}>
          Start Simulation
        </button>
      ) : simStatus === 'running' ? (
        <button onClick={pauseSim} style={btnStyle(theme.signalAmber, false)}>Pause</button>
      ) : simStatus === 'paused' ? (
        <button onClick={resumeSim} style={btnStyle(theme.signalGreen, false)}>Resume</button>
      ) : null}

      {runId && simStatus !== 'idle' && (
        <button onClick={handleReset} style={btnStyle(theme.signalRed, false)}>Reset</button>
      )}

      {/* Speed selector */}
      {runId && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ fontSize: 11, color: theme.textMuted }}>Speed:</span>
          {speeds.map((s) => (
            <button
              key={s}
              onClick={() => handleSpeedChange(s)}
              style={{
                padding: '4px 8px', border: 'none', borderRadius: 4,
                fontSize: 11, fontWeight: 600, cursor: 'pointer',
                background: s === speed ? theme.accent : theme.border,
                color: s === speed ? '#fff' : theme.textSecondary,
              }}
            >
              {s}x
            </button>
          ))}
        </div>
      )}

      {/* EV Start/End + Dispatch — when simulation running but no EV */}
      {runId && simStatus === 'running' && !evDispatched && !state?.ev && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <select
            value={startIntersection}
            onChange={(e) => setStartIntersection(e.target.value)}
            style={{ ...selectStyle, fontSize: 11, padding: '4px 6px', maxWidth: 140 }}
            title="Start intersection"
          >
            <option value="">Start: auto</option>
            {intersectionConfigs.map((c) => (
              <option key={c.intersection_id} value={c.intersection_id}>
                {c.name}
              </option>
            ))}
          </select>
          <span style={{ fontSize: 11, color: theme.textMuted }}>to</span>
          <select
            value={endIntersection}
            onChange={(e) => setEndIntersection(e.target.value)}
            style={{ ...selectStyle, fontSize: 11, padding: '4px 6px', maxWidth: 140 }}
            title="End intersection"
          >
            <option value="">End: auto</option>
            {intersectionConfigs.map((c) => (
              <option key={c.intersection_id} value={c.intersection_id}>
                {c.name}
              </option>
            ))}
          </select>
          <button onClick={handleDispatchEV} style={{
            ...btnStyle(theme.accent, true),
            animation: 'pulse-btn 2s infinite',
          }}>
            Dispatch Ambulance
          </button>
        </div>
      )}

      {/* EV already dispatched indicator */}
      {evDispatched && evActive && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '4px 12px', borderRadius: 6,
          background: theme.accent + '15', border: `1px solid ${theme.accent}40`,
        }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: theme.accent,
            animation: 'pulse-dot 1s infinite',
          }} />
          <span style={{ fontSize: 12, color: theme.accent, fontWeight: 600 }}>
            AMB_01 en route
          </span>
        </div>
      )}

      {evStatus === 'arrived' && (
        <div style={{
          padding: '4px 12px', borderRadius: 6,
          background: theme.signalGreen + '15', border: `1px solid ${theme.signalGreen}40`,
        }}>
          <span style={{ fontSize: 12, color: theme.signalGreen, fontWeight: 600 }}>
            Ambulance arrived at destination
          </span>
        </div>
      )}

      {/* Status indicator — right side */}
      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
        {state?.controller_type && (
          <span style={{
            fontSize: 10, padding: '2px 8px', borderRadius: 4,
            background: state.controller_type === 'mcts' ? theme.accent + '20' : theme.border,
            color: state.controller_type === 'mcts' ? theme.accent : theme.textSecondary,
          }}>
            {state.controller_type.toUpperCase()}
          </span>
        )}
        <span style={{
          fontSize: 10, padding: '2px 8px', borderRadius: 4,
          background: simStatus === 'running' ? theme.signalGreen + '20' : theme.border,
          color: simStatus === 'running' ? theme.signalGreen : theme.textSecondary,
          fontWeight: 600,
        }}>
          {simStatus.toUpperCase()}
        </span>
      </div>

      {error && (
        <div style={{ width: '100%', fontSize: 12, color: theme.signalRed, marginTop: 4 }}>
          {error}
        </div>
      )}

      <style>{`
        @keyframes pulse-btn {
          0%, 100% { box-shadow: 0 0 0 0 ${theme.accent}40; }
          50% { box-shadow: 0 0 0 8px ${theme.accent}00; }
        }
        @keyframes pulse-dot {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
};

const btnStyle = (color: string, prominent: boolean): React.CSSProperties => ({
  padding: prominent ? '8px 18px' : '6px 14px',
  border: 'none', borderRadius: 6,
  background: color, color: '#fff',
  fontSize: prominent ? 14 : 13,
  fontWeight: 700,
  cursor: 'pointer', whiteSpace: 'nowrap',
});

const selectStyle: React.CSSProperties = {
  padding: '6px 10px', borderRadius: 6, border: `1px solid ${theme.border}`,
  background: theme.cardBg, color: theme.textPrimary, fontSize: 13,
};
