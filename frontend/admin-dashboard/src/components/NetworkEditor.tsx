import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { theme } from '@inc/shared-ui';
import type { IntersectionConfig, LinkConfig, CorridorConfig } from '../types';
import { getIntersections, getCorridors, loadConfig } from '../api/client';

const W = 820;
const H = 560;
const PAD = 50;
const NODE_R = 16;

interface NodePos {
  id: string;
  name: string;
  x: number;
  y: number;
  enabled: boolean;
}

function projectLatLon(configs: IntersectionConfig[], enabled: Set<string>): NodePos[] {
  if (configs.length === 0) return [];
  const lats = configs.map((c) => c.lat);
  const lons = configs.map((c) => c.lon);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLon = Math.min(...lons);
  const maxLon = Math.max(...lons);
  const latRange = maxLat - minLat || 0.001;
  const lonRange = maxLon - minLon || 0.001;

  return configs.map((c) => ({
    id: c.intersection_id,
    name: c.name,
    x: PAD + ((c.lon - minLon) / lonRange) * (W - 2 * PAD),
    y: PAD + ((maxLat - c.lat) / latRange) * (H - 2 * PAD),
    enabled: enabled.has(c.intersection_id),
  }));
}

export const NetworkEditor: React.FC = () => {
  const [configs, setConfigs] = useState<IntersectionConfig[]>([]);
  const [links, setLinks] = useState<LinkConfig[]>([]);
  const [corridorConfig, setCorridorConfig] = useState<CorridorConfig | null>(null);
  const [enabled, setEnabled] = useState<Set<string>>(new Set());
  const [startNode, setStartNode] = useState('');
  const [endNode, setEndNode] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);

  useEffect(() => {
    getIntersections()
      .then((cfgs) => {
        setConfigs(cfgs);
        setEnabled(new Set(cfgs.map((c) => c.intersection_id)));
      })
      .catch(() => {});
    getCorridors()
      .then((corridors) => {
        if (corridors.length > 0) {
          setCorridorConfig(corridors[0]);
          setLinks(corridors[0].links);
          const ids = corridors[0].intersection_ids;
          if (ids.length >= 2) {
            setStartNode(ids[0]);
            setEndNode(ids[ids.length - 1]);
          }
        }
      })
      .catch(() => {});
  }, []);

  const nodes = useMemo(() => projectLatLon(configs, enabled), [configs, enabled]);
  const nodeMap = useMemo(() => {
    const m = new Map<string, NodePos>();
    nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes]);

  const toggleNode = useCallback((id: string) => {
    setEnabled((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        if (startNode === id) setStartNode('');
        if (endNode === id) setEndNode('');
      } else {
        next.add(id);
      }
      return next;
    });
  }, [startNode, endNode]);

  const handleSave = async () => {
    if (!corridorConfig) return;
    try {
      const enabledIds = configs
        .filter((c) => enabled.has(c.intersection_id))
        .map((c) => c.intersection_id);
      const enabledLinks = links.filter(
        (l) => enabled.has(l.from_intersection) && enabled.has(l.to_intersection)
      );

      // Save updated corridor
      await loadConfig('corridor', {
        corridor: {
          ...corridorConfig,
          intersection_ids: enabledIds,
          links: enabledLinks,
        },
      });

      // Save only enabled intersections
      const enabledConfigs = configs.filter((c) => enabled.has(c.intersection_id));
      await loadConfig('intersections', { intersections: enabledConfigs });

      setStatus('Saved');
      setTimeout(() => setStatus(null), 3000);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    }
  };

  const enabledLinks = links.filter(
    (l) => enabled.has(l.from_intersection) && enabled.has(l.to_intersection)
  );

  return (
    <div>
      <div style={{ display: 'flex', gap: 16, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 600 }}>Start:</label>
          <select
            value={startNode}
            onChange={(e) => setStartNode(e.target.value)}
            style={selectStyle}
          >
            <option value="">-- select --</option>
            {configs.filter((c) => enabled.has(c.intersection_id)).map((c) => (
              <option key={c.intersection_id} value={c.intersection_id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <label style={{ fontSize: 12, color: theme.textSecondary, fontWeight: 600 }}>End:</label>
          <select
            value={endNode}
            onChange={(e) => setEndNode(e.target.value)}
            style={selectStyle}
          >
            <option value="">-- select --</option>
            {configs.filter((c) => enabled.has(c.intersection_id)).map((c) => (
              <option key={c.intersection_id} value={c.intersection_id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <button onClick={handleSave} style={btnPrimary}>
          Save Network
        </button>
        <button
          onClick={() => setEnabled(new Set(configs.map((c) => c.intersection_id)))}
          style={btnSecondary}
        >
          Enable All
        </button>
        <button onClick={() => setEnabled(new Set())} style={btnSecondary}>
          Disable All
        </button>
        <span style={{ fontSize: 11, color: theme.textMuted }}>
          {enabled.size}/{configs.length} nodes | {enabledLinks.length} links
        </span>
        {status && (
          <span style={{
            fontSize: 12,
            color: status.startsWith('Error') ? theme.signalRed : theme.signalGreen,
          }}>
            {status}
          </span>
        )}
      </div>

      <div style={{ fontSize: 11, color: theme.textMuted, marginBottom: 8 }}>
        Click nodes to enable/disable. Use dropdowns to set EV start and end points.
      </div>

      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        style={{
          maxWidth: W,
          background: theme.bg,
          borderRadius: 8,
          border: `1px solid ${theme.border}`,
        }}
      >
        {/* Links */}
        {links.map((link, i) => {
          const from = nodeMap.get(link.from_intersection);
          const to = nodeMap.get(link.to_intersection);
          if (!from || !to) return null;
          const active = from.enabled && to.enabled;
          return (
            <line
              key={`link-${i}`}
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke={active ? '#475569' : '#1e293b'}
              strokeWidth={active ? 3 : 1}
              opacity={active ? 0.7 : 0.3}
            />
          );
        })}

        {/* Nodes */}
        {nodes.map((pos) => {
          const isStart = pos.id === startNode;
          const isEnd = pos.id === endNode;
          const isHovered = pos.id === hovered;
          const borderColor = isStart
            ? theme.signalGreen
            : isEnd
              ? theme.signalRed
              : pos.enabled
                ? theme.accent
                : '#334155';

          return (
            <g
              key={pos.id}
              style={{ cursor: 'pointer' }}
              onClick={() => toggleNode(pos.id)}
              onMouseEnter={() => setHovered(pos.id)}
              onMouseLeave={() => setHovered(null)}
            >
              {/* Hover ring */}
              {isHovered && (
                <circle cx={pos.x} cy={pos.y} r={NODE_R + 6}
                  fill="none" stroke={borderColor} strokeWidth={1.5} opacity={0.4} />
              )}
              {/* Start/End badge ring */}
              {(isStart || isEnd) && (
                <circle cx={pos.x} cy={pos.y} r={NODE_R + 4}
                  fill="none" stroke={borderColor} strokeWidth={2.5} opacity={0.6}
                  strokeDasharray={isEnd ? '4,3' : 'none'} />
              )}
              {/* Node circle */}
              <circle
                cx={pos.x} cy={pos.y} r={NODE_R}
                fill={pos.enabled ? '#0f172a' : '#0a0e1a'}
                stroke={borderColor}
                strokeWidth={2}
                opacity={pos.enabled ? 1 : 0.4}
              />
              {/* Inner dot */}
              <circle cx={pos.x} cy={pos.y} r={5}
                fill={pos.enabled ? borderColor : '#334155'}
                opacity={pos.enabled ? 0.8 : 0.3} />
              {/* Start/End label */}
              {isStart && (
                <text x={pos.x} y={pos.y - NODE_R - 8} textAnchor="middle"
                  fontSize={9} fill={theme.signalGreen} fontWeight={700}>
                  START
                </text>
              )}
              {isEnd && (
                <text x={pos.x} y={pos.y - NODE_R - 8} textAnchor="middle"
                  fontSize={9} fill={theme.signalRed} fontWeight={700}>
                  END
                </text>
              )}
              {/* Name */}
              <text
                x={pos.x} y={pos.y + NODE_R + 14}
                textAnchor="middle" fontSize={8}
                fill={pos.enabled ? theme.textPrimary : theme.textMuted}
                fontWeight={pos.enabled ? 600 : 400}
              >
                {pos.name}
              </text>
            </g>
          );
        })}

        {/* Legend */}
        <g transform="translate(10, 10)">
          <rect width={130} height={76} rx={6} fill={theme.cardBg} opacity={0.9} stroke={theme.border} />
          <text x={10} y={14} fontSize={9} fill={theme.textSecondary} fontWeight={600}>Legend</text>
          {[
            { color: theme.accent, label: 'Enabled node' },
            { color: '#334155', label: 'Disabled node' },
            { color: theme.signalGreen, label: 'Start point' },
            { color: theme.signalRed, label: 'End point' },
          ].map((item, i) => (
            <g key={item.label} transform={`translate(10, ${26 + i * 13})`}>
              <circle cx={4} cy={0} r={4} fill={item.color} />
              <text x={14} y={3} fontSize={8} fill={theme.textMuted}>{item.label}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  );
};

const selectStyle: React.CSSProperties = {
  padding: '4px 8px', borderRadius: 6, border: `1px solid ${theme.border}`,
  background: theme.cardBg, color: theme.textPrimary, fontSize: 12,
};

const btnPrimary: React.CSSProperties = {
  padding: '6px 16px', border: 'none', borderRadius: 6,
  background: theme.accent, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer',
};

const btnSecondary: React.CSSProperties = {
  padding: '6px 12px', border: `1px solid ${theme.border}`, borderRadius: 6,
  background: theme.cardBg, color: theme.textSecondary, fontSize: 11, fontWeight: 600, cursor: 'pointer',
};
