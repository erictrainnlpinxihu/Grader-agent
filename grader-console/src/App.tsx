import { useEffect, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import { Layout } from '@arco-design/web-react';
import { SideNav, AppHeader } from './components/layout/AppLayout';
import { DebugChatPage } from './pages/DebugChatPage';
import { TracePage } from './pages/TracePage';
import { ApprovalQueuePage } from './pages/ApprovalQueuePage';
import { EvalPage } from './pages/EvalPage';
import { fetchHealth } from './api/manifest';

const Content = Layout.Content;

export default function App() {
  const [collapsed, setCollapsed] = useState(false);
  const [healthy, setHealthy] = useState<boolean | null>(null);

  useEffect(() => {
    let alive = true;
    fetchHealth()
      .then(() => alive && setHealthy(true))
      .catch(() => alive && setHealthy(false));
    return () => {
      alive = false;
    };
  }, []);

  return (
    <Layout style={{ height: '100vh' }}>
      <SideNav collapsed={collapsed} />
      <Layout>
        <AppHeader healthy={healthy} onToggle={() => setCollapsed((c) => !c)} />
        <Content style={{ overflow: 'auto', background: 'var(--clr-bg-page)' }}>
          <Routes>
            <Route path="/" element={<DebugChatPage />} />
            <Route path="/trace" element={<TracePage />} />
            <Route path="/approvals" element={<ApprovalQueuePage />} />
            <Route path="/eval" element={<EvalPage />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
}
