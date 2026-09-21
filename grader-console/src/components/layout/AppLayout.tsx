import { useNavigate, useLocation } from 'react-router-dom';
import { Layout, Menu, Tag, Button } from '@arco-design/web-react';

const Sider = Layout.Sider;
const Header = Layout.Header;

const NAV_ITEMS = [
  { key: '/', label: '调试台' },
  { key: '/trace', label: 'Trace 回放' },
  { key: '/approvals', label: '审批队列' },
  { key: '/eval', label: 'Eval 回归' },
];

interface SideNavProps {
  collapsed: boolean;
}

export function SideNav({ collapsed }: SideNavProps) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Sider
      collapsed={collapsed}
      collapsible={false}
      style={{ background: 'var(--clr-bg-card)', borderRight: '1px solid var(--clr-border)' }}
    >
      <div style={{ height: 48, display: 'flex', alignItems: 'center', padding: '0 20px', fontWeight: 600 }}>
        {collapsed ? 'G' : 'Grader 控制台'}
      </div>
      <Menu
        selectedKeys={[location.pathname]}
        onClickMenuItem={(key) => navigate(key)}
        style={{ borderRight: 'none' }}
      >
        {NAV_ITEMS.map((item) => (
          <Menu.Item key={item.key} style={{ paddingLeft: collapsed ? 0 : 20 }}>
            {item.label}
          </Menu.Item>
        ))}
      </Menu>
    </Sider>
  );
}

interface AppHeaderProps {
  healthy: boolean | null;
  onToggle: () => void;
}

export function AppHeader({ healthy, onToggle }: AppHeaderProps) {
  return (
    <Header
      style={{
        background: 'var(--clr-bg-card)',
        borderBottom: '1px solid var(--clr-border)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 20px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <Button size="small" onClick={onToggle} aria-label="toggle nav">
          ☰
        </Button>
        <span style={{ fontWeight: 600 }}>Grader 调试控制台</span>
        <Tag size="small" color="gray">dev</Tag>
      </div>
      <div>
        {healthy === null ? (
          <Tag size="small">连接中…</Tag>
        ) : healthy ? (
          <Tag size="small" color="green">
            后端已连接
          </Tag>
        ) : (
          <Tag size="small" color="red">
            后端未连接
          </Tag>
        )}
      </div>
    </Header>
  );
}
