import { ContextBar } from '../components/chat/ContextBar';
import { ChatPanel } from '../components/chat/ChatPanel';
import { DecisionPath } from '../components/trace/DecisionPath';
import { PipelineBrief } from '../components/layout/PipelineBrief';
import { useSession } from '../store/session';

export function DebugChatPage() {
  const selected = useSession((s) => s.selectedResp);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 首页展示：五阶段链路简介（可展开） */}
      <PipelineBrief />
      <div className="console-grid" style={{ flex: 1, minHeight: 0, height: 'auto' }}>
        <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          <ContextBar />
          <div style={{ flex: 1, minHeight: 0 }}>
            <ChatPanel />
          </div>
        </div>
        <div className="scroll-area" style={{ minHeight: 0, paddingRight: 4 }}>
          <DecisionPath resp={selected} />
        </div>
      </div>
    </div>
  );
}
