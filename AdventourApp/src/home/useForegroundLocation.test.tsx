import React from 'react';
import renderer, { act } from 'react-test-renderer';
import axios from 'axios';
import Geolocation from '@react-native-community/geolocation';
import useForegroundLocation from './useForegroundLocation';

let appStateListener: ((state: string) => void) | undefined;
const mockRequestMultiple = jest.fn();
const mockPermissionCheck = jest.fn();
const mockPosition = jest.fn();

jest.mock('react-native', () => ({
  AppState: {
    currentState: 'active',
    addEventListener: jest.fn((_event: string, listener: (state: string) => void) => {
      appStateListener = listener;
      return { remove: jest.fn() };
    }),
  },
  Platform: { OS: 'android' },
  PermissionsAndroid: {
    PERMISSIONS: { ACCESS_COARSE_LOCATION: 'coarse', ACCESS_FINE_LOCATION: 'fine' },
    RESULTS: { GRANTED: 'granted' },
    requestMultiple: (...args: unknown[]) => mockRequestMultiple(...args),
    check: (...args: unknown[]) => mockPermissionCheck(...args),
  },
}));
jest.mock('@react-native-community/geolocation', () => ({
  __esModule: true,
  default: { getCurrentPosition: (...args: unknown[]) => mockPosition(...args), setRNConfiguration: jest.fn() },
}));
jest.mock('axios', () => ({ get: jest.fn() }));
jest.mock('../Config', () => ({ __esModule: true, default: { BACKEND_BASE_URL: 'http://test' } }));

type Controller = ReturnType<typeof useForegroundLocation>;
const deferred = <T,>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(next => { resolve = next; });
  return { promise, resolve };
};

const Probe = ({ controller, userId = 1, homeCity, onResolved, onUnavailable, onAcquiring }: {
  controller: React.MutableRefObject<Controller | null>; userId?: number | null; homeCity?: string | null;
  onResolved: jest.Mock; onUnavailable: jest.Mock; onAcquiring: jest.Mock;
}) => {
  controller.current = useForegroundLocation({ userId, homeCity, onResolved, onUnavailable, onAcquiring });
  return null;
};

const granted = { coarse: 'granted', fine: 'granted' };
const denied = { coarse: 'denied', fine: 'denied' };
const position = (latitude = 28.5, longitude = -81.4, timestamp = Date.now()) => ({
  coords: { latitude, longitude }, timestamp,
});

const renderHook = (homeCity?: string | null, userId: number | null = 1) => {
  const controller = { current: null } as React.MutableRefObject<Controller | null>;
  const onResolved = jest.fn();
  const onUnavailable = jest.fn();
  const onAcquiring = jest.fn();
  let view!: renderer.ReactTestRenderer;
  act(() => {
    view = renderer.create(<Probe controller={controller} userId={userId} homeCity={homeCity} onResolved={onResolved} onUnavailable={onUnavailable} onAcquiring={onAcquiring} />);
  });
  return { controller, onResolved, onUnavailable, onAcquiring, view };
};

const settle = async () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

beforeEach(() => {
  jest.clearAllMocks();
  appStateListener = undefined;
  mockRequestMultiple.mockResolvedValue(granted);
  mockPermissionCheck.mockResolvedValue(false);
});

afterEach(() => jest.restoreAllMocks());

test('commits a fresh coarse GPS fix with its reverse locality label', async () => {
  jest.mocked(axios.get).mockResolvedValue({ data: { city: 'Orlando', state: 'Florida' } });
  const { onResolved, view } = renderHook();
  await settle();
  expect(mockPosition.mock.calls[0][2]).toEqual(expect.objectContaining({ enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 }));
  await act(async () => mockPosition.mock.calls[0][0](position()));
  expect(onResolved).toHaveBeenCalledWith({ coordinates: { latitude: 28.5, longitude: -81.4 }, label: 'Orlando, Florida', origin: 'gps' });
  view.unmount();
});

test('coarse-only Android permission requests the network-compatible low-accuracy provider', async () => {
  mockRequestMultiple.mockResolvedValue({ coarse: 'granted', fine: 'denied' });
  const { view } = renderHook();
  await settle();
  expect(mockPosition.mock.calls[0][2]).toEqual(expect.objectContaining({ enableHighAccuracy: false, timeout: 15000, maximumAge: 10000 }));
  view.unmount();
});

test('retains usable GPS when reverse lookup fails', async () => {
  jest.mocked(axios.get).mockRejectedValue(new Error('offline'));
  const { onResolved, view } = renderHook();
  await settle();
  await act(async () => mockPosition.mock.calls[0][0](position()));
  expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ label: 'Current Location', origin: 'gps' }));
  view.unmount();
});

test('denied permission resolves only a locality-qualified home label', async () => {
  mockRequestMultiple.mockResolvedValue(denied);
  jest.mocked(axios.get).mockResolvedValue({ data: { latitude: 43.65, longitude: -79.38, description: 'Toronto, Ontario (City)' } });
  const { onResolved, view } = renderHook('Toronto, Ontario');
  await settle();
  expect(axios.get).toHaveBeenCalledWith('http://test/geocode', expect.objectContaining({
    params: { address: 'Toronto, Ontario', locality_only: 'true' },
  }));
  expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ origin: 'home', label: 'Toronto, Ontario' }));
  view.unmount();
});

test('denied permission without a home makes no lookup and reports unavailable', async () => {
  mockRequestMultiple.mockResolvedValue(denied);
  const { onUnavailable, view } = renderHook();
  await settle();
  expect(axios.get).not.toHaveBeenCalled();
  expect(onUnavailable).toHaveBeenCalledTimes(1);
  view.unmount();
});

test('a denied automatic permission does not prompt again until explicit GPS retry', async () => {
  mockRequestMultiple.mockResolvedValue(denied);
  const { controller, view } = renderHook();
  await settle();
  act(() => appStateListener?.('background'));
  act(() => appStateListener?.('active'));
  await settle();
  expect(mockRequestMultiple).toHaveBeenCalledTimes(1);
  expect(mockPermissionCheck).toHaveBeenCalledTimes(2);
  await act(async () => { await controller.current?.retry(); });
  await settle();
  expect(mockRequestMultiple).toHaveBeenCalledTimes(2);
  view.unmount();
});

test.each([-10001, 1000])('stale or future fixes fall back to home', async offset => {
  jest.mocked(axios.get).mockResolvedValue({ data: { latitude: 43.65, longitude: -79.38, city: 'Toronto', state: 'Ontario' } });
  const { onResolved, view } = renderHook('Toronto, Ontario');
  await settle();
  await act(async () => mockPosition.mock.calls[0][0](position(28.5, -81.4, Date.now() + offset)));
  expect(onResolved).toHaveBeenCalledWith(expect.objectContaining({ origin: 'home' }));
  view.unmount();
});

test('manual intent wins over pending GPS and home failure callbacks', async () => {
  mockRequestMultiple.mockResolvedValue(denied);
  const home = deferred<{ data: unknown }>();
  jest.mocked(axios.get).mockReturnValue(home.promise as any);
  const { controller, onResolved, onUnavailable, view } = renderHook('Toronto, Ontario');
  await settle();
  act(() => controller.current?.invalidate(true));
  home.resolve({ data: { latitude: 43.65, longitude: -79.38 } });
  await settle();
  expect(onResolved).not.toHaveBeenCalled();
  expect(onUnavailable).not.toHaveBeenCalled();
  view.unmount();
});

test('account change cancels an older pending fix and starts a new acquisition', async () => {
  const { onResolved, onAcquiring, controller, view } = renderHook();
  await settle();
  await act(async () => view.update(<Probe controller={controller} userId={2} onResolved={onResolved} onUnavailable={jest.fn()} onAcquiring={onAcquiring} />));
  await settle();
  await act(async () => mockPosition.mock.calls[0][0](position()));
  expect(onResolved).not.toHaveBeenCalled();
  expect(mockPosition).toHaveBeenCalledTimes(2);
  view.unmount();
});

test('account logout clears the previous account launch state', async () => {
  const { onAcquiring, controller, view } = renderHook();
  await settle();
  await act(async () => view.update(<Probe controller={controller} userId={null} onResolved={jest.fn()} onUnavailable={jest.fn()} onAcquiring={onAcquiring} />));
  expect(onAcquiring).toHaveBeenCalledTimes(2);
  view.unmount();
});

test('permission-dialog inactive/active does not duplicate acquisition, but genuine background clears and refreshes automatic state', async () => {
  const { controller, onAcquiring, onResolved, view } = renderHook();
  await settle();
  const oldPositionCallback = mockPosition.mock.calls[0][0];
  act(() => appStateListener?.('inactive'));
  act(() => appStateListener?.('active'));
  expect(mockRequestMultiple).toHaveBeenCalledTimes(1);
  act(() => appStateListener?.('background'));
  expect(onAcquiring).toHaveBeenCalledTimes(2);
  act(() => appStateListener?.('active'));
  await settle();
  expect(mockRequestMultiple).toHaveBeenCalledTimes(2);
  await act(async () => oldPositionCallback(position()));
  expect(onResolved).not.toHaveBeenCalled();
  act(() => controller.current?.invalidate(true));
  act(() => appStateListener?.('background'));
  act(() => appStateListener?.('active'));
  await settle();
  expect(mockRequestMultiple).toHaveBeenCalledTimes(2);
  view.unmount();
});
