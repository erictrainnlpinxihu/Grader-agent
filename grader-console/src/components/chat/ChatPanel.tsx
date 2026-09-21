import { useState } from 'react';
import { Input, Button, Spin, Message } from '@arco-design/web-react';
import { sendChat } from '../../api/chat';
import { defaultUserId, useSession } from '../../store/session';
import type { ChatRequest } from '../../api/types';
import type { ExampleQuestion } from '../../examples/questions';
import { ExampleQuestions } from './ExampleQuestions';
import { MessageBubble } from './MessageBubble';

export function ChatPanel() {
  const ctx = useSession((s) => s.ctx);
  const sessionId = useSession((s) => s.sessionId);
  const turns = useSession((s) => s.turns);
  const pushUserTurn = useSession((s) => s.pushUserTurn);
  const pushAssistantTurn = useSession((s) => s.pushAssistantTurn);
  const setRole = useSession((s) => s.setRole);

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);

  async function run(
    text: string,
    claimedRole?: string,
    ctxOverride?: Partial<Omit<ChatRequest, 'text'>>,
  ) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    pushUserTurn(trimmed);
    try {
      const resp = await sendChat({
        ...ctx,
        ...ctxOverride,
        session_id: sessionId,
        text: trimmed,
        ...(claimedRole ? { claimed_role: claimedRole } : {}),
      });
      pushAssistantTurn(resp);
    } catch (e) {
      Message.error(e instanceof Error ? e.message : '请求失败');
    } finally {
      setLoading(false);
      setInput('');
    }
  }

  async function handlePick(q: ExampleQuestion) {
    // 点击示例自动切角色；setState 是异步的，本次请求要用 override 立即生效，
    // 否则会拿旧角色发出去（stale closure）。
    let override: Partial<Omit<ChatRequest, 'text'>> | undefined;
    if (q.role && q.role !== ctx.role) {
      setRole(q.role);
      override = { role: q.role, user_id: defaultUserId(q.role) };
    }
    // 多轮综合场景：按顺序依次发送，每轮等待响应后再发下一轮
    for (const t of q.texts ?? [q.text]) {
      await run(t, q.claimed_role, override);
    }
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="scroll-area" style={{ flex: 1, paddingRight: 4 }}>
        <ExampleQuestions onPick={handlePick} />
        {turns.length === 0 && !loading && (
          <div className="muted small" style={{ padding: 24, textAlign: 'center' }}>
            点击上方示例问题，或在下方输入框开始调试
          </div>
        )}
        {turns.map((turn, i) => (
          <MessageBubble key={i} turn={turn} sessionId={sessionId} />
        ))}
        {loading && (
          <div style={{ marginBottom: 12 }}>
            <Spin size={16} /> <span className="small muted">Agent 正在决策…</span>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', gap: 8, paddingTop: 8, borderTop: '1px solid var(--clr-border-light)' }}>
        <Input.TextArea
          placeholder="输入问题，回车发送（Shift+R 换行）"
          value={input}
          onChange={setInput}
          autoSize={{ minRows: 1, maxRows: 4 }}
          onPressEnter={(e) => {
            if (!e.shiftKey) {
              e.preventDefault();
              run(input);
            }
          }}
        />
        <Button type="primary" loading={loading} onClick={() => run(input)}>
          发送
        </Button>
      </div>
    </div>
  );
}
