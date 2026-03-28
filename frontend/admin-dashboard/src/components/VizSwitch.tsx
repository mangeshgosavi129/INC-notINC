import React, { useState } from 'react';
import { theme } from '@inc/shared-ui';
import { CorridorGraph } from './CorridorGraph';
import type { IntersectionState, EVState } from '../types';

interface Props {
  intersections: IntersectionState[];
  ev: EVState | null;
}

// Lazy load LeafletMap only when user switches to map mode — avoids Leaflet CSS/icon issues on load
const LazyLeafletMap = React.lazy(() =>
  import('./LeafletMap').then((m) => ({ default: m.LeafletMap }))
);

export const VizSwitch: React.FC<Props> = ({ intersections, ev }) => {
  const [mode, setMode] = useState<'graph' | 'map'>('graph');

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', width: '100%' }}>
      <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
        {(['graph', 'map'] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            style={{
              padding: '4px 12px', border: 'none', borderRadius: 4,
              background: mode === m ? theme.accent : theme.border,
              color: mode === m ? '#fff' : theme.textSecondary,
              fontSize: 12, fontWeight: 600, cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {m}
          </button>
        ))}
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        {mode === 'graph' ? (
          <CorridorGraph intersections={intersections} ev={ev} />
        ) : (
          <React.Suspense fallback={<div style={{ padding: 20, color: theme.textMuted }}>Loading map...</div>}>
            <LazyLeafletMap intersections={intersections} ev={ev} />
          </React.Suspense>
        )}
      </div>
    </div>
  );
};
