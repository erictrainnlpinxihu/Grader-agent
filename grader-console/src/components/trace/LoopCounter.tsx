import { Tag } from '@arco-design/web-react';

const LIMIT = 6; // 后端 RECURSION_LIMIT

export function LoopCounter({ count }: { count: number }) {
  const nearLimit = count >= LIMIT;
  return (
    <Tag color={nearLimit ? 'red' : 'blue'}>
      ReAct 循环 {count} / {LIMIT}
    </Tag>
  );
}
