import React, { useState, useEffect } from 'react';
import { theme } from '@inc/shared-ui';
import { getConfig, loadConfig, resetConfig } from '../api/client';
import { NetworkEditor } from '../components/NetworkEditor';

const tabs = ['network', 'intersections', 'corridor', 'mcts', 'simulation'] as const;
type Tab = typeof tabs[number];

export const ConfigPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<Tab>('network');
  const [configData, setConfigData] = useState<Record<string, any>>({});
  const [editText, setEditText] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getConfig().then((data) => {
      setConfigData(data);
      setEditText(JSON.stringify(data[activeTab] ?? {}, null, 2));
      setLoading(false);
    }).catch((e) => {
      setStatus(`Failed to load config: ${e.message}`);
      setLoading(false);
    });
  }, []);

  useEffect(() => {
    if (Object.keys(configData).length > 0) {
      setEditText(JSON.stringify(configData[activeTab] ?? {}, null, 2));
    }
  }, [activeTab, configData]);

  const handleSave = async () => {
    try {
      const parsed = JSON.parse(editText);

      // Backend expects wrapped format for intersections and corridor
      let payload = parsed;
      if (activeTab === 'intersections') {
        // If user edited the flat array, wrap it
        payload = Array.isArray(parsed) ? { intersections: parsed } : parsed;
      } else if (activeTab === 'corridor') {
        // If user edited the flat dict (has corridor_id), wrap it
        payload = parsed.corridor_id ? { corridor: parsed } : parsed;
      }

      await loadConfig(activeTab, payload);
      setConfigData((prev) => ({ ...prev, [activeTab]: parsed }));
      setStatus('Saved successfully');
      setTimeout(() => setStatus(null), 3000);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    }
  };

  const handleReset = async () => {
    try {
      await resetConfig();
      const data = await getConfig();
      setConfigData(data);
      setStatus('Reset to defaults');
      setTimeout(() => setStatus(null), 3000);
    } catch (e: any) {
      setStatus(`Error: ${e.message}`);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, color: theme.textMuted, textAlign: 'center' }}>
        Loading configuration...
      </div>
    );
  }

  return (
    <div style={{ padding: 24, maxWidth: 900, margin: '0 auto' }}>
      <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 16, color: theme.textPrimary }}>
        Configuration
      </h1>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 16 }}>
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            style={{
              padding: '6px 16px', border: 'none', borderRadius: 6,
              background: activeTab === t ? theme.accent : theme.cardBg,
              color: activeTab === t ? '#fff' : theme.textSecondary,
              fontSize: 13, fontWeight: 600, cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Network Editor tab */}
      {activeTab === 'network' ? (
        <NetworkEditor />
      ) : (
        <>
          {/* JSON Editor */}
          <textarea
            value={editText}
            onChange={(e) => setEditText(e.target.value)}
            style={{
              width: '100%', height: 450, fontFamily: theme.fontMono, fontSize: 12,
              background: theme.cardBg, color: theme.textPrimary, border: `1px solid ${theme.border}`,
              borderRadius: 8, padding: 16, resize: 'vertical', lineHeight: 1.6,
              outline: 'none',
            }}
            spellCheck={false}
          />

          {/* Actions */}
          <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center' }}>
            <button onClick={handleSave} style={btnStyle(theme.accent)}>Save</button>
            <button onClick={handleReset} style={btnStyle(theme.signalAmber)}>Reset to Defaults</button>
            {status && (
              <span style={{
                fontSize: 12, marginLeft: 12,
                color: status.startsWith('Error') ? theme.signalRed : theme.signalGreen,
              }}>
                {status}
              </span>
            )}
          </div>
        </>
      )}
    </div>
  );
};

const btnStyle = (bg: string): React.CSSProperties => ({
  padding: '8px 20px', border: 'none', borderRadius: 6,
  background: bg, color: '#fff', fontSize: 13, fontWeight: 600, cursor: 'pointer',
});
