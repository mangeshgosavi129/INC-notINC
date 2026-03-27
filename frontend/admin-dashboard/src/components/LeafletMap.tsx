import React, { useEffect, useState, useMemo } from 'react';
import { MapContainer, TileLayer, CircleMarker, Polyline, Popup, Marker, Tooltip, useMap } from 'react-leaflet';
import L from 'leaflet';
import { signalColor, theme } from '@inc/shared-ui';
import type { IntersectionState, EVState, IntersectionConfig, LinkConfig } from '../types';
import { getIntersections, getCorridors } from '../api/client';

import 'leaflet/dist/leaflet.css';

interface Props {
  intersections: IntersectionState[];
  ev: EVState | null;
}

function createEvIcon() {
  return L.divIcon({
    html: `<div style="
      width: 32px; height: 32px; border-radius: 50%;
      background: radial-gradient(circle, ${theme.accent} 40%, ${theme.accent}00 70%);
      border: 3px solid #fff;
      box-shadow: 0 0 20px ${theme.accent}, 0 0 40px ${theme.accent}60;
      display: flex; align-items: center; justify-content: center;
      font-size: 16px; color: #fff;
    ">+</div>`,
    iconSize: [32, 32],
    iconAnchor: [16, 16],
    className: '',
  });
}

function EVMarkerDynamic({
  ev,
  links,
  configMap,
}: {
  ev: EVState;
  links: LinkConfig[];
  configMap: Map<string, IntersectionConfig>;
}) {
  if (ev.status === 'idle' || ev.status === 'arrived') return null;
  const li = ev.current_link_index;
  if (li < 0 || li >= links.length) return null;

  const link = links[li];
  const from = configMap.get(link.from_intersection);
  const to = configMap.get(link.to_intersection);
  if (!from || !to) return null;

  const t = ev.position_on_link;
  const lat = from.lat + (to.lat - from.lat) * t;
  const lng = from.lon + (to.lon - from.lon) * t;

  return <Marker position={[lat, lng]} icon={createEvIcon()} />;
}

function FitBounds({ coords }: { coords: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (coords.length > 1) {
      map.fitBounds(coords, { padding: [50, 50] });
    }
  }, []);
  return null;
}

export const LeafletMap: React.FC<Props> = ({ intersections, ev }) => {
  const [configs, setConfigs] = useState<IntersectionConfig[]>([]);
  const [links, setLinks] = useState<LinkConfig[]>([]);

  useEffect(() => {
    getIntersections().then(setConfigs).catch(() => {});
    getCorridors()
      .then((corridors) => {
        if (corridors.length > 0) setLinks(corridors[0].links);
      })
      .catch(() => {});
  }, []);

  const configMap = useMemo(() => {
    const m = new Map<string, IntersectionConfig>();
    configs.forEach((c) => m.set(c.intersection_id, c));
    return m;
  }, [configs]);

  if (configs.length === 0) {
    return <div style={{ padding: 20, color: theme.textSecondary }}>Loading map data...</div>;
  }

  const coords: [number, number][] = configs.map((c) => [c.lat, c.lon]);

  return (
    <MapContainer
      center={[configs[0].lat, configs[0].lon]}
      zoom={13}
      style={{ width: '100%', height: '100%', minHeight: 350, borderRadius: 8 }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/">OSM</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />
      <FitBounds coords={coords} />

      {/* Network links */}
      {links.map((link, i) => {
        const from = configMap.get(link.from_intersection);
        const to = configMap.get(link.to_intersection);
        if (!from || !to) return null;

        const toIx = intersections.find((x) => x.intersection_id === link.to_intersection);
        const totalQ = toIx ? Object.values(toIx.queues).reduce((a, b) => a + b, 0) : 0;
        const qPct = Math.min(totalQ / 40, 1);
        const qColor =
          qPct > 0.7
            ? theme.signalRed
            : qPct > 0.4
              ? theme.signalAmber
              : '#475569';

        return (
          <Polyline
            key={`link-${i}`}
            positions={[
              [from.lat, from.lon],
              [to.lat, to.lon],
            ]}
            color={qColor}
            weight={qPct > 0.4 ? 6 : 4}
            opacity={0.6}
          />
        );
      })}

      {/* Intersection markers */}
      {configs.map((cfg) => {
        const ix = intersections.find((x) => x.intersection_id === cfg.intersection_id);
        const color = ix ? signalColor(ix.state) : theme.textMuted;
        const totalQ = ix ? Object.values(ix.queues).reduce((a, b) => a + b, 0) : 0;
        const evHere = ev?.waiting_at === cfg.intersection_id;

        return (
          <CircleMarker
            key={cfg.intersection_id}
            center={[cfg.lat, cfg.lon]}
            radius={evHere ? 14 : 10}
            fillColor={color}
            fillOpacity={0.9}
            color={evHere ? '#fff' : color}
            weight={evHere ? 4 : 2}
          >
            <Tooltip permanent direction="top" offset={[0, -14]} className="">
              <div
                style={{
                  background: '#0f172a',
                  color: '#f1f5f9',
                  padding: '3px 8px',
                  borderRadius: 4,
                  fontSize: 9,
                  fontWeight: 600,
                  border: `1px solid ${color}`,
                  whiteSpace: 'nowrap',
                }}
              >
                {cfg.name}
              </div>
            </Tooltip>
            <Popup>
              <div style={{ fontFamily: "'Inter', sans-serif", fontSize: 12, lineHeight: 1.6 }}>
                <strong style={{ fontSize: 14 }}>{cfg.name}</strong>
                <br />
                <span style={{ color: '#666' }}>ID:</span> {cfg.intersection_id}
                <br />
                <span style={{ color: '#666' }}>Signal:</span>{' '}
                <b style={{ color }}>{ix?.state ?? 'N/A'}</b> (Phase {ix?.phase ?? '-'})
                <br />
                <span style={{ color: '#666' }}>Queue:</span> {totalQ.toFixed(1)} vehicles
                <br />
                <span style={{ color: '#666' }}>Green for:</span>{' '}
                {ix?.green_movements?.join(', ') ?? 'none'}
              </div>
            </Popup>
          </CircleMarker>
        );
      })}

      {/* EV marker */}
      {ev && ev.status !== 'idle' && (
        <EVMarkerDynamic ev={ev} links={links} configMap={configMap} />
      )}
    </MapContainer>
  );
};
