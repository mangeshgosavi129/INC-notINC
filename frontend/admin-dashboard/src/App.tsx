import React from 'react';
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { SimulationProvider } from './context/SimulationContext';
import { SimulationPage } from './pages/SimulationPage';
import { ConfigPage } from './pages/ConfigPage';
import { ComparisonPage } from './pages/ComparisonPage';
import { HistoryPage } from './pages/HistoryPage';
import { theme } from '@inc/shared-ui';

const navItems = [
  { path: '/', label: 'Simulation', icon: '>' },
  { path: '/config', label: 'Config', icon: '#' },
  { path: '/compare', label: 'Compare', icon: '=' },
  { path: '/history', label: 'History', icon: '@' },
];

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div style={{ padding: 40, color: '#ef4444', fontFamily: 'monospace', fontSize: 14 }}>
          <h2 style={{ marginBottom: 12 }}>Something crashed</h2>
          <pre style={{ whiteSpace: 'pre-wrap', background: '#111827', padding: 16, borderRadius: 8 }}>
            {this.state.error.message}
            {'\n\n'}
            {this.state.error.stack}
          </pre>
          <button
            onClick={() => { this.setState({ error: null }); window.location.reload(); }}
            style={{ marginTop: 16, padding: '8px 20px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <SimulationProvider>
          <div style={{ display: 'flex', height: '100vh', overflow: 'hidden' }}>
            {/* Sidebar */}
            <nav style={{
              width: 200, background: theme.cardBg, borderRight: `1px solid ${theme.border}`,
              display: 'flex', flexDirection: 'column', padding: '16px 0', flexShrink: 0,
            }}>
              <div style={{
                padding: '0 16px 16px', fontSize: 15, fontWeight: 700,
                color: theme.accent, letterSpacing: 0.5,
                borderBottom: `1px solid ${theme.border}`, marginBottom: 8,
              }}>
                INC Control
              </div>

              {navItems.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  end={item.path === '/'}
                  style={({ isActive }) => ({
                    display: 'flex', alignItems: 'center', gap: 10,
                    padding: '10px 16px', textDecoration: 'none',
                    color: isActive ? theme.accent : theme.textSecondary,
                    background: isActive ? theme.accent + '10' : 'transparent',
                    borderLeft: isActive ? `3px solid ${theme.accent}` : '3px solid transparent',
                    fontSize: 13, fontWeight: isActive ? 600 : 400,
                    transition: 'all 0.15s ease',
                  })}
                >
                  <span style={{ fontFamily: theme.fontMono, fontSize: 14 }}>{item.icon}</span>
                  {item.label}
                </NavLink>
              ))}

              <div style={{ flex: 1 }} />
              <div style={{ padding: '12px 16px', fontSize: 10, color: theme.textMuted }}>
                Dynamic Corridor Clearing<br />RH-MCTS v0.1
              </div>
            </nav>

            {/* Main content */}
            <main style={{ flex: 1, overflow: 'hidden' }}>
              <ErrorBoundary>
                <Routes>
                  <Route path="/" element={<SimulationPage />} />
                  <Route path="/config" element={<ConfigPage />} />
                  <Route path="/compare" element={<ComparisonPage />} />
                  <Route path="/history" element={<HistoryPage />} />
                </Routes>
              </ErrorBoundary>
            </main>
          </div>
        </SimulationProvider>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
