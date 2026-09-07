import React from 'react';
import renderer from 'react-test-renderer';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Config from '../Config';
import PilotFeedback from './PilotFeedback';
import { flushPilot, pilotConfig, pilotPost, submitPilot } from './PilotService';

jest.mock('react-native-config', () => ({ APP_VARIANT: 'standard' }));
jest.mock('react-native-get-random-values', () => ({}));
jest.mock('uuid', () => ({ v4: () => '6a5e39e6-0542-440d-9b94-8028227da64a' }));
jest.mock('axios', () => ({ post: jest.fn(), isAxiosError: () => false }));
jest.mock('@react-native-async-storage/async-storage', () => ({ getItem: jest.fn(), setItem: jest.fn() }));
jest.mock('../services/AuthService', () => ({ getCurrentUser: jest.fn(async () => ({ firebase_uid: 'tester' })) }));
jest.mock('@react-navigation/native', () => ({ useIsFocused: () => true }));

beforeEach(() => { jest.clearAllMocks(); Config.PILOT_BUILD = false; });

test('standard build with a stale pilot decision renders nothing and does no study IO', async () => {
  const view = renderer.create(<PilotFeedback decisionId="known-pilot-decision" title="Cafe" />);
  expect(view.toJSON()).toBeNull();
  expect(await pilotConfig()).toEqual({});
  await flushPilot();
  await expect(pilotPost('known-pilot-decision', 'invite', {})).rejects.toThrow('disabled');
  expect(axios.post).not.toHaveBeenCalled();
  expect(AsyncStorage.getItem).not.toHaveBeenCalled();
  expect(AsyncStorage.setItem).not.toHaveBeenCalled();
});

test('pilot build without a server-issued decision offers no study controls', () => {
  Config.PILOT_BUILD = true;
  expect(renderer.create(<PilotFeedback title="Cafe" />).toJSON()).toBeNull();
  expect(axios.post).not.toHaveBeenCalled();
});

test('offline answer persists, then retries the same answer identity once connected', async () => {
  Config.PILOT_BUILD = true; Config.PILOT_ID = 'test'; Config.APP_BUILD_ID = 'build';
  const storage = new Map<string, string>();
  jest.mocked(AsyncStorage.getItem).mockImplementation(async key => storage.get(key) || null);
  jest.mocked(AsyncStorage.setItem).mockImplementation(async (key, value) => { storage.set(key, value); });
  jest.mocked(axios.post).mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: { status: 'saved' } });
  const answer = { id: 'stable-answer-id', value: 0, answer_kind: 'rated' };
  expect(await submitPilot('decision', 'feedback', answer)).toBe('pending');
  expect([...storage.entries()].find(([key]) => key.startsWith('pilot-outbox'))?.[1]).toContain('stable-answer-id');
  await flushPilot();
  expect(axios.post).toHaveBeenCalledTimes(2);
  expect(jest.mocked(axios.post).mock.calls[0][1]).toEqual(answer);
  expect(jest.mocked(axios.post).mock.calls[1][1]).toEqual(answer);
  expect([...storage.entries()].find(([key]) => key.startsWith('pilot-outbox'))?.[1]).toBe('[]');
});
