import axios from 'axios';

// 开发期经 vite 代理 /api -> http://localhost:8000
// Agent 决策 / 批改 / 检索 / eval 全集回归可能较慢，180s 内均属正常
export const api = axios.create({
  baseURL: '/api',
  timeout: 180000,
});

api.interceptors.response.use(
  (resp) => resp,
  (error) => {
    const msg =
      error?.response?.data?.detail || error?.message || '请求失败';
    return Promise.reject(new Error(typeof msg === 'string' ? msg : JSON.stringify(msg)));
  },
);
