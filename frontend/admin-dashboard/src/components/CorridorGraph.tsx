import React, { useEffect, useState, useMemo } from 'react';
import { theme, signalColor } from '@inc/shared-ui';
import type { IntersectionState, EVState, IntersectionConfig, LinkConfig } from '../types';
import { getIntersections, getCorridors } from '../api/client';

interface Props {
  intersections: IntersectionState[];
  ev: EVState | null;
}

interface NodePos {
  id: string;
  name: string;
  x: number;
  y: number;
}

const NODE_R = 14;
const W = 960;
const H = 640;
const PAD = 40;

function projectLatLon(configs: IntersectionConfig[]): NodePos[] {
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
    // Flip Y: higher lat = lower y
    y: PAD + ((maxLat - c.lat) / latRange) * (H - 2 * PAD),
  }));
}

export const CorridorGraph: React.FC<Props> = ({ intersections, ev }) => {
  const [configs, setConfigs] = useState<IntersectionConfig[]>([]);
  const [links, setLinks] = useState<LinkConfig[]>([]);

  useEffect(() => {
    getIntersections()
      .then(setConfigs)
      .catch(() => {});
    getCorridors()
      .then((corridors) => {
        if (corridors.length > 0) setLinks(corridors[0].links);
      })
      .catch(() => {});
  }, []);

  const nodes = useMemo(() => projectLatLon(configs), [configs]);
  const nodeMap = useMemo(() => {
    const m = new Map<string, NodePos>();
    nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes]);

  const stateMap = useMemo(() => {
    const m = new Map<string, IntersectionState>();
    intersections.forEach((ix) => m.set(ix.intersection_id, ix));
    return m;
  }, [intersections]);

  // EV position: find the link it's on and interpolate
  const evPos = useMemo(() => {
    if (!ev || ev.status === 'idle' || ev.status === 'arrived') return null;
    const li = ev.current_link_index;
    if (li < 0 || li >= links.length) return null;
    const link = links[li];
    const from = nodeMap.get(link.from_intersection);
    const to = nodeMap.get(link.to_intersection);
    if (!from || !to) return null;
    const t = ev.position_on_link;
    return {
      x: from.x + (to.x - from.x) * t,
      y: from.y + (to.y - from.y) * t,
    };
  }, [ev, links, nodeMap]);

  return (
    <svg
      width="100%"
      height="100%"
      viewBox={`0 0 ${W} ${H}`}
      style={{ maxWidth: W, maxHeight: H }}
    >
      <defs>
        <filter id="neon">
          <feGaussianBlur stdDeviation="3" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="evGlow">
          <feGaussianBlur stdDeviation="6" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* Links */}
      {links.map((link, i) => {
        const from = nodeMap.get(link.from_intersection);
        const to = nodeMap.get(link.to_intersection);
        if (!from || !to) return null;

        const toIx = stateMap.get(link.to_intersection);
        const totalQ = toIx
          ? Object.values(toIx.queues).reduce((a, b) => a + b, 0)
          : 0;
        const qPct = Math.min(totalQ / 40, 1);
        const qColor =
          qPct > 0.7
            ? theme.signalRed
            : qPct > 0.4
              ? theme.signalAmber
              : theme.signalGreen;

        return (
          <g key={`link-${i}`}>
            {/* Road shadow */}
            <line
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke="#0a0e1a" strokeWidth={8} strokeLinecap="round"
            />
            {/* Road surface */}
            <line
              x1={from.x} y1={from.y} x2={to.x} y2={to.y}
              stroke="#1e293b" strokeWidth={5} strokeLinecap="round"
            />
            {/* Queue heat */}
            {qPct > 0.05 && (
              <line
                x1={from.x} y1={from.y} x2={to.x} y2={to.y}
                stroke={qColor} strokeWidth={5} strokeLinecap="round"
                opacity={qPct * 0.5}
              />
            )}
            {/* Distance label */}
            <text
              x={(from.x + to.x) / 2}
              y={(from.y + to.y) / 2 - 6}
              textAnchor="middle"
              fontSize={7}
              fill={theme.textMuted}
              opacity={0.6}
            >
              {link.length_meters}m
            </text>
          </g>
        );
      })}

      {/* Intersection nodes */}
      {nodes.map((pos) => {
        const ix = stateMap.get(pos.id);
        if (!ix) {
          // Draw placeholder node (no sim state yet)
          return (
            <g key={pos.id}>
              <circle
                cx={pos.x} cy={pos.y} r={NODE_R}
                fill="#0f172a" stroke={theme.border} strokeWidth={2}
              />
              <text
                x={pos.x} y={pos.y + NODE_R + 12}
                textAnchor="middle" fontSize={7} fill={theme.textMuted}
              >
                {pos.name}
              </text>
            </g>
          );
        }

        const color = signalColor(ix.state);
        const totalQ = Object.values(ix.queues).reduce((a, b) => a + b, 0);
        const evWaiting = ev?.waiting_at === ix.intersection_id;

        return (
          <g key={ix.intersection_id}>
            {/* Outer glow */}
            <circle
              cx={pos.x} cy={pos.y} r={NODE_R + 4}
              fill="none" stroke={color} strokeWidth={1.5} opacity={0.3}
              filter="url(#neon)"
            />
            {/* Background */}
            <circle
              cx={pos.x} cy={pos.y} r={NODE_R}
              fill="#0f172a" stroke={color} strokeWidth={2}
            />
            {/* Inner signal light */}
            <circle cx={pos.x} cy={pos.y} r={6} fill={color} opacity={0.9}>
              {ix.state === 'GREEN' && (
                <animate
                  attributeName="opacity"
                  values="0.9;0.5;0.9"
                  dur="1.5s"
                  repeatCount="indefinite"
                />
              )}
            </circle>
            {/* EV waiting indicator */}
            {evWaiting && (
              <circle
                cx={pos.x} cy={pos.y} r={NODE_R + 8}
                fill="none" stroke={theme.signalRed} strokeWidth={2}
                strokeDasharray="4,3"
              >
                <animate
                  attributeName="stroke-dashoffset"
                  values="0;14"
                  dur="1s"
                  repeatCount="indefinite"
                />
              </circle>
            )}
            {/* Name */}
            <text
              x={pos.x} y={pos.y + NODE_R + 12}
              textAnchor="middle" fontSize={7} fill={theme.textPrimary}
              fontWeight={600}
            >
              {pos.name}
            </text>
            {/* Queue count */}
            <text
              x={pos.x} y={pos.y + NODE_R + 21}
              textAnchor="middle" fontSize={6} fill={theme.textMuted}
            >
              Q:{totalQ.toFixed(0)}
            </text>
          </g>
        );
      })}

      {/* EV vehicle */}
      {evPos && (
        <g filter="url(#evGlow)">
          <rect
            x={evPos.x - 12} y={evPos.y - 8} width={24} height={16}
            rx={4} fill={theme.accent} stroke="#fff" strokeWidth={1.5}
          />
          {/* Red cross */}
          <rect x={evPos.x - 1.5} y={evPos.y - 4} width={3} height={8} rx={0.5} fill="#fff" />
          <rect x={evPos.x - 4} y={evPos.y - 1.5} width={8} height={3} rx={0.5} fill="#fff" />
          {/* Label */}
          <text
            x={evPos.x} y={evPos.y - 14} textAnchor="middle"
            fontSize={8} fill={theme.accent} fontWeight={700}
          >
            EV
          </text>
          {/* Pulse */}
          <circle cx={evPos.x} cy={evPos.y} r={16} fill="none" stroke={theme.accent} strokeWidth={1.5}>
            <animate attributeName="r" values="12;22;12" dur="1.2s" repeatCount="indefinite" />
            <animate attributeName="opacity" values="0.6;0;0.6" dur="1.2s" repeatCount="indefinite" />
          </circle>
        </g>
      )}

      {/* Legend */}
      <g transform="translate(10, 10)">
        <rect
          width={110} height={60} rx={6}
          fill={theme.cardBg} opacity={0.9} stroke={theme.border}
        />
        <text x={10} y={14} fontSize={8} fill={theme.textSecondary} fontWeight={600}>
          Signal State
        </text>
        {[
          { color: theme.signalGreen, label: 'Green (GO)' },
          { color: theme.signalAmber, label: 'Amber' },
          { color: theme.signalRed, label: 'Red (STOP)' },
        ].map((item, i) => (
          <g key={item.label} transform={`translate(10, ${26 + i * 12})`}>
            <circle cx={4} cy={0} r={3} fill={item.color} />
            <text x={12} y={3} fontSize={7} fill={theme.textMuted}>
              {item.label}
            </text>
          </g>
        ))}
      </g>

      {/* Node count */}
      <text x={W - 10} y={H - 10} textAnchor="end" fontSize={8} fill={theme.textMuted}>
        {nodes.length} intersections | {links.length} links
      </text>
    </svg>
  );
};
