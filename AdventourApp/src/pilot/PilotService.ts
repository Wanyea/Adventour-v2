import 'react-native-get-random-values';
import { v4 as uuid } from 'uuid';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Config from '../Config';
import AuthService from '../services/AuthService';

export type Invitation = {
  id: string; question: 'appeal_v1' | 'relevance_v1'; interest?: string;
  source: 'sampled' | 'voluntary'; status: 'offered' | 'skipped' | 'answered';
};
let sessionWork: Promise<unknown> = Promise.resolve();
export const pilotConfig = async () => {
  if (!Config.PILOT_BUILD) { return {}; }
  const user = await AuthService.getCurrentUser();
  if (!user) { return {}; }
  const task = sessionWork.then(async () => {
    const key = `pilot-session-v1:${Config.BACKEND_BASE_URL}:${Config.PILOT_ID}:${user.firebase_uid}`;
    const prior = JSON.parse(await AsyncStorage.getItem(key) || 'null');
    const value = { id: prior && Date.now() - prior.lastActive < 1800000 ? prior.id : uuid(), lastActive: Date.now() };
    await AsyncStorage.setItem(key, JSON.stringify(value));
    return value.id as string;
  });
  sessionWork = task.catch(() => {});
  const session = await task;
  return { headers: {
    'X-Adventour-Pilot': Config.PILOT_ID, 'X-Adventour-Build': Config.APP_BUILD_ID,
    'X-Adventour-Session': session,
    'X-Adventour-Timezone': Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  }};
};

export const pilotPost = async (decision: string, operation: string, data: object) => {
  if (!Config.PILOT_BUILD) { throw new Error('Pilot collection is disabled'); }
  const result = await axios.post(`${Config.BACKEND_BASE_URL}/api/pilot/decisions/${decision}/${operation}`,
    data, { ...await pilotConfig(), timeout: 10000 });
  return result.data;
};

type Job = { id: string; decision: string; operation: string; data: object; state?: 'rejected' };
let work: Promise<unknown> = Promise.resolve();
const serial = <T,>(task: () => Promise<T>): Promise<T> => {
  const next = work.then(task, task);
  work = next.catch(() => {});
  return next;
};

// Keys isolate study/backend/account. Standard builds never read or flush this queue.
const queueKey = async () => {
  if (!Config.PILOT_BUILD) { return null; }
  const user = await AuthService.getCurrentUser();
  return user ? `pilot-outbox-v1:${Config.BACKEND_BASE_URL}:${Config.PILOT_ID}:${user.firebase_uid}` : null;
};

async function deliver(key: string, jobs: Job[], target?: string) {
  let targetState: 'saved' | 'pending' | 'rejected' = 'pending';
  const remaining: Job[] = [];
  for (const job of jobs) {
    if (job.state === 'rejected') { remaining.push(job); continue; }
    // An account switch must not upload the prior account's records.
    if (await queueKey() !== key) { remaining.push(job); continue; }
    try {
      await pilotPost(job.decision, job.operation, job.data);
      if (job.id === target) { targetState = 'saved'; }
    } catch (error) {
      const status = axios.isAxiosError(error) ? error.response?.status : undefined;
      const rejected = status === 400 || status === 403 || status === 404;
      remaining.push(rejected ? { ...job, state: 'rejected' } : job);
      if (job.id === target) { targetState = rejected ? 'rejected' : 'pending'; }
    }
  }
  await AsyncStorage.setItem(key, JSON.stringify(remaining));
  return targetState;
}

export const submitPilot = (decision: string, operation: string, data: object) => serial(async () => {
  const key = await queueKey();
  if (!key) { throw new Error('Pilot sign-in required'); }
  const jobs: Job[] = JSON.parse(await AsyncStorage.getItem(key) || '[]');
  const job = { id: uuid(), decision, operation, data };
  jobs.push(job);
  await AsyncStorage.setItem(key, JSON.stringify(jobs));
  return deliver(key, jobs, job.id);
});

export const flushPilot = () => serial(async () => {
  const key = await queueKey();
  if (key) { await deliver(key, JSON.parse(await AsyncStorage.getItem(key) || '[]')); }
});

export const signalPilot = (decision: string, kind: string, duration = 0) =>
  pilotPost(decision, 'signals', { id: uuid(), kind, duration_ms: duration, occurred_at: new Date().toISOString() });
