import React from 'react';
import { theme } from '@inc/shared-ui';
import type { DirectionInfo } from '../types';

interface Props {
  directions: DirectionInfo | null;
}

export const DirectionsBanner: React.FC<Props> = ({ directions }) => {
  if (!directions) return null;

  return (
    <div style={{
      margin: '0 12px 12px',
      padding: '16px',
      background: theme.cardBg,
      borderRadius: '8px',
      border: `1px solid ${theme.border}`,
      display: 'flex',
      alignItems: 'center',
      gap: '16px',
      boxShadow: '0 2px 4px rgba(0,0,0,0.05)'
    }}>
      {/* Icon */}
      <div style={{
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        width: '40px', height: '40px', borderRadius: '50%',
        background: theme.accent + '20', color: theme.accent, fontSize: '24px'
      }}>
        ↑
      </div>

      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '4px' }}>
          <div style={{ fontSize: '18px', fontWeight: 800, color: theme.textPrimary }}>
            {directions.distance_remaining_m}m
          </div>
          <div style={{ fontSize: '12px', color: theme.textMuted, fontWeight: 600 }}>
            Total left: {directions.total_distance_remaining_m}m
          </div>
        </div>
        <div style={{ fontSize: '14px', color: theme.textSecondary, fontWeight: 500 }}>
          {directions.heading} on {directions.current_link}
        </div>
        <div style={{ fontSize: '12px', color: theme.textMuted, marginTop: '2px' }}>
          Toward {directions.next_intersection_name}
        </div>
      </div>
    </div>
  );
};
