import axios from 'axios';
import AuthService, { User } from './AuthService';

jest.mock('axios', () => ({
  put: jest.fn(),
  interceptors: { request: { use: jest.fn() } },
}));
jest.mock('../Config', () => ({ API_AUTH_MODE: 'dev', DEV_AUTH_EMAIL: 'fallback@example.com' }));
jest.mock('@react-native-firebase/auth', () => jest.fn());
jest.mock('@react-native-async-storage/async-storage', () => ({ getItem: jest.fn(), setItem: jest.fn(), removeItem: jest.fn() }));
jest.mock('@react-native-google-signin/google-signin', () => ({ GoogleSignin: { configure: jest.fn() }, statusCodes: {} }));

const user = (firebase_uid: string): User => ({
  id: firebase_uid === 'a' ? 1 : 2,
  firebase_uid,
  email: `${firebase_uid}@example.com`,
  username: firebase_uid,
  display_name: firebase_uid,
});

const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => { resolve = nextResolve; });
  return { promise, resolve };
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(console, 'error').mockImplementation(() => undefined);
  (AuthService as any).currentUser = null;
  (AuthService as any).sessionVersion = 0;
});

afterEach(() => jest.restoreAllMocks());

test('a deferred profile response cannot replace a newer account session or its token', async () => {
  const response = deferred<{ data: { user: User } }>();
  jest.mocked(axios.put).mockReturnValue(response.promise);
  (AuthService as any).setCurrentUser(user('a'));

  const updatingA = AuthService.updateProfile({ home_city: 'Accra, Ghana' });
  await Promise.resolve();
  await Promise.resolve();
  expect(axios.put).toHaveBeenCalledTimes(1);
  (AuthService as any).setCurrentUser(user('b'));
  response.resolve({ data: { user: { ...user('a'), home_city: 'Accra, Ghana' } } });

  await expect(updatingA).rejects.toThrow('completed');
  expect(await AuthService.getCurrentUser()).toEqual(user('b'));
  await expect(AuthService.getIdToken()).resolves.toBe('dev:b@example.com');
});

test('a same-account auth callback does not invalidate a normal profile save', async () => {
  const response = deferred<{ data: { user: User } }>();
  jest.mocked(axios.put).mockReturnValue(response.promise);
  (AuthService as any).setCurrentUser(user('a'));

  const updatingA = AuthService.updateProfile({ home_city: 'Accra, Ghana' });
  (AuthService as any).setCurrentUser({ ...user('a'), profile_picture: 'wanyea' });
  const saved = { ...user('a'), home_city: 'Accra, Ghana' };
  response.resolve({ data: { user: saved } });

  await expect(updatingA).resolves.toEqual(saved);
  expect(await AuthService.getCurrentUser()).toEqual(saved);
});
