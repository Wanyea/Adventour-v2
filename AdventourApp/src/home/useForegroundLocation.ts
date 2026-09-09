import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, PermissionsAndroid, Platform } from 'react-native';
import Geolocation from '@react-native-community/geolocation';
import axios from 'axios';
import Config from '../Config';
import { Coordinates, LocationMode } from './homeUtils';

const FIX_TIMEOUT_MS = 15000;
const MAX_FIX_AGE_MS = 10000;

type Resolution = { coordinates: Coordinates; label: string; origin: Extract<LocationMode, 'gps' | 'home'> };
type PermissionLevel = 'fine' | 'coarse' | false;
type Options = {
  userId?: number | string | null;
  homeCity?: string | null;
  onResolved: (value: Resolution) => void;
  onUnavailable: () => void;
  onAcquiring: () => void;
};

const usableCoordinates = (latitude: unknown, longitude: unknown): latitude is number =>
  typeof latitude === 'number' && Number.isFinite(latitude) && Math.abs(latitude) <= 90
  && typeof longitude === 'number' && Number.isFinite(longitude) && Math.abs(longitude) <= 180;

const labelFor = (data: { description?: string; city?: string; state?: string }) => {
  const description = data.description?.replace(/\s+\((City|Town|Village|Hamlet|Neighborhood|State|Country|District|Locality|County|Street)\)$/, '');
  return description || [data.city, data.state].filter(Boolean).join(', ') || 'Current Location';
};

export default function useForegroundLocation({ userId, homeCity, onResolved, onUnavailable, onAcquiring }: Options) {
  const version = useRef(0);
  const manual = useRef(false);
  const account = useRef<number | string | null | undefined>(undefined);
  const automaticPermissionDenied = useRef(false);
  const backgrounded = useRef(false);
  const [acquiring, setAcquiring] = useState(false);
  const callbacks = useRef({ onResolved, onUnavailable, onAcquiring });
  callbacks.current = { onResolved, onUnavailable, onAcquiring };

  const invalidate = useCallback((manualIntent = false) => {
    version.current += 1;
    if (manualIntent) {manual.current = true;}
  }, []);

  const resolveHome = useCallback(async (request: number) => {
    if (!homeCity?.trim()) {return false;}
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
        params: { address: homeCity.trim(), locality_only: 'true' }, timeout: FIX_TIMEOUT_MS,
      });
      const { latitude, longitude } = response.data;
      if (request !== version.current || !usableCoordinates(latitude, longitude)) {return false;}
      callbacks.current.onResolved({
        coordinates: { latitude, longitude }, label: labelFor(response.data), origin: 'home',
      });
      return true;
    } catch {
      return false;
    }
  }, [homeCity]);

  const fallbackToHome = useCallback(async (request: number) => {
    const resolved = await resolveHome(request);
    if (request === version.current && !resolved) {callbacks.current.onUnavailable();}
    if (request === version.current) {setAcquiring(false);}
  }, [resolveHome]);

  const requestPermission = useCallback(async (explicit: boolean): Promise<PermissionLevel> => {
    if (Platform.OS !== 'android') {return 'fine';}
    if (automaticPermissionDenied.current && !explicit) {
      const [coarse, fine] = await Promise.all([
        PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION),
        PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION),
      ]);
      const level: PermissionLevel = fine ? 'fine' : coarse ? 'coarse' : false;
      if (level) {automaticPermissionDenied.current = false;}
      return level;
    }
    const result = await PermissionsAndroid.requestMultiple([
      PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
      PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
    ]);
    const level: PermissionLevel = result[PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION] === PermissionsAndroid.RESULTS.GRANTED
      ? 'fine'
      : result[PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION] === PermissionsAndroid.RESULTS.GRANTED ? 'coarse' : false;
    automaticPermissionDenied.current = !level;
    return level;
  }, []);

  const acquire = useCallback(async (explicit = false) => {
    const request = ++version.current;
    if (explicit) {manual.current = false;}
    if (!userId) {
      callbacks.current.onAcquiring();
      setAcquiring(false);
      return;
    }
    if (!explicit && manual.current) {return;}
    callbacks.current.onAcquiring();
    setAcquiring(true);
    let permission: PermissionLevel = false;
    try {
      permission = await requestPermission(explicit);
    } catch {
      automaticPermissionDenied.current = true;
      permission = false;
    }
    if (request !== version.current || !permission) {
      if (request === version.current) {
        await fallbackToHome(request);
      }
      return;
    }
    Geolocation.getCurrentPosition(async position => {
      const { latitude, longitude } = position.coords;
      const age = Date.now() - position.timestamp;
      const fresh = Number.isFinite(position.timestamp) && age >= 0 && age <= MAX_FIX_AGE_MS;
      if (request !== version.current || !fresh || !usableCoordinates(latitude, longitude)) {
        if (request === version.current) {
          await fallbackToHome(request);
        }
        return;
      }
      try {
        const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
          params: { latitude, longitude }, timeout: FIX_TIMEOUT_MS,
        });
        if (request !== version.current) {return;}
        callbacks.current.onResolved({ coordinates: { latitude, longitude }, label: labelFor(response.data), origin: 'gps' });
        setAcquiring(false);
      } catch {
        if (request === version.current) {
          callbacks.current.onResolved({ coordinates: { latitude, longitude }, label: 'Current Location', origin: 'gps' });
          setAcquiring(false);
        }
      }
    }, async () => {
      if (request === version.current) {
        await fallbackToHome(request);
      }
    }, { enableHighAccuracy: Platform.OS === 'android' && permission === 'fine', timeout: FIX_TIMEOUT_MS, maximumAge: MAX_FIX_AGE_MS });
  }, [fallbackToHome, requestPermission, userId]);

  useEffect(() => {
    Geolocation.setRNConfiguration({
      authorizationLevel: 'whenInUse',
      enableBackgroundLocationUpdates: false,
      skipPermissionRequests: false,
    });
    if (account.current !== userId) {
      account.current = userId;
      manual.current = false;
      automaticPermissionDenied.current = false;
    }
    acquire();
    return () => { version.current += 1; };
  }, [acquire, userId]);

  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'background') {
        backgrounded.current = true;
        if (!manual.current) {
          version.current += 1;
          callbacks.current.onAcquiring();
          setAcquiring(true);
        }
      }
      if (state === 'active' && backgrounded.current) {
        backgrounded.current = false;
        if (!manual.current) {acquire();}
      }
    });
    return () => subscription.remove();
  }, [acquire]);

  return { retry: () => acquire(true), invalidate, acquiring };
}
