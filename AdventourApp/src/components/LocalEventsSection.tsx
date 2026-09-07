import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, AppState, Linking, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import axios from 'axios';
import Config from '../Config';
import { Coordinates } from '../home/homeUtils';
import PilotFeedback from '../pilot/PilotFeedback';
import { pilotConfig, signalPilot } from '../pilot/PilotService';

type LocalEvent = {
  pilot_decision_id?: string;
  source_id: string; occurrence_id: string; title: string; starts_at: string; ends_at: string;
  timezone: string; venue_name: string; latitude: number; longitude: number;
  source_name?: string; official_url: string; access_note: string;
  verified_at: string; expires_at: string;
};

function EventCard({ event, children }: { event: LocalEvent; children: React.ReactNode }) {
  const cardRef = useRef<View>(null);
  if (!Config.PILOT_BUILD || !event.pilot_decision_id) { return <View style={styles.event}>{children}</View>; }
  return <View><View ref={cardRef} style={styles.event}>{children}</View>
    <PilotFeedback decisionId={event.pilot_decision_id} title={event.title} cardRef={cardRef} />
  </View>;
}

const when = (event: LocalEvent) => {
  const date = new Date(event.starts_at).toLocaleDateString('en-US', {
    timeZone: event.timezone, weekday: 'short', month: 'short', day: 'numeric',
  });
  const time = (value: string) => new Date(value).toLocaleTimeString('en-US', {
    timeZone: event.timezone, hour: 'numeric', minute: '2-digit', timeZoneName: 'short',
  });
  return `${date} · ${time(event.starts_at)}–${time(event.ends_at)}`;
};

const LocalEventsSection = ({ coordinates }: { coordinates: Coordinates }) => {
  const [events, setEvents] = useState<LocalEvent[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [checking, setChecking] = useState<string | null>(null);
  const [clock, setClock] = useState(Date.now());
  const serverOffset = useRef(0);
  const focused = useIsFocused();
  const requestId = useRef(0);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const load = useCallback(async (capture = false) => {
    const id = ++requestId.current;
    setBusy(true);
    try {
      const result = await axios.get(`${Config.BACKEND_BASE_URL}/api/local-events`, {
        ...(capture ? await pilotConfig() : {}),
        params: { ...coordinates, radius_meters: 50000 }, timeout: 15000,
      });
      if (id !== requestId.current) return;
      serverOffset.current = Date.parse(result.data.checked_at) - Date.now();
      setClock(Date.now() + serverOffset.current);
      setEvents(previous => result.data.events.map((item: LocalEvent) => {
        if (capture) { return item; }
        const prior = previous.find(p => p.source_id === item.source_id && p.occurrence_id === item.occurrence_id);
        const fields: (keyof LocalEvent)[] = ['title','starts_at','ends_at','timezone','venue_name',
          'latitude','longitude','official_url','access_note','verified_at','expires_at'];
        return prior && fields.every(field => prior[field] === item[field]) ?
          { ...item, pilot_decision_id: prior.pilot_decision_id } : item;
      }));
      setError('');
    } catch {
      if (id === requestId.current) {
        setEvents([]);
        setError('Events could not be refreshed. Try again.');
      }
    } finally {
      if (id === requestId.current) setBusy(false);
    }
  }, [coordinates.latitude, coordinates.longitude]);

  useEffect(() => {
    setEvents([]);
    setExpanded(false);
    if (focused) load(true);
    const refresh = setInterval(() => {
      if (focused && AppState.currentState === 'active') load();
    }, 60000);
    const tick = setInterval(() => setClock(Date.now() + serverOffset.current), 1000);
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active' && focused) load();
    });
    return () => { ++requestId.current; clearInterval(refresh); clearInterval(tick); subscription.remove(); };
  }, [load, focused]);

  const open = async (event: LocalEvent) => {
    setChecking(event.occurrence_id);
    try {
      const config = await pilotConfig();
      const result = await axios.post(`${Config.BACKEND_BASE_URL}/api/local-events/${encodeURIComponent(event.source_id)}/${encodeURIComponent(event.occurrence_id)}/verify`, {}, {
        ...config, headers: { ...config.headers, ...(event.pilot_decision_id ? { 'X-Adventour-Decision': event.pilot_decision_id } : {}) }, timeout: 45000 });
      if (!mounted.current) return;
      const fresh: LocalEvent = result.data.event;
      setEvents(previous => previous.map(item => item.source_id === fresh.source_id && item.occurrence_id === fresh.occurrence_id ? { ...item, ...fresh } : item));
      const follow = (url: string) => {
        if (!mounted.current) return;
        if (Date.now() + serverOffset.current >= Math.min(Date.parse(fresh.ends_at), Date.parse(fresh.expires_at))) {
          Alert.alert('Check this event again', 'The event check has expired.');
          load();
          return;
        }
        if (fresh.pilot_decision_id) {
          signalPilot(fresh.pilot_decision_id, url === fresh.official_url ? 'open_source' : 'navigate').catch(() => {});
        }
        openLink(url);
      };
      Alert.alert(fresh.title, `${when(fresh)}\n${fresh.venue_name}\n\n${fresh.access_note}`, [
        { text: 'Close', style: 'cancel' },
        { text: 'Organizer details', onPress: () => follow(fresh.official_url) },
        { text: 'Directions', onPress: () => follow(`https://www.google.com/maps/dir/?api=1&destination=${fresh.latitude},${fresh.longitude}`) },
      ]);
    } catch (err) {
      if (!mounted.current) return;
      const message = axios.isAxiosError(err) ? err.response?.data?.error : null;
      Alert.alert('Event check', message || 'Could not check the organizer. Try again before leaving.');
      load();
    } finally { setChecking(null); }
  };
  const openLink = (url: string) => Linking.openURL(url).catch(() => Alert.alert('Could not open link', 'Please try again.'));
  const current = events.filter(event => Math.min(Date.parse(event.ends_at), Date.parse(event.expires_at),
    Date.parse(event.verified_at) + 86400000) > clock);

  return (
    <View style={styles.section}>
      <View style={styles.heading}>
        <Text style={styles.title}>Upcoming local events</Text>
        <TouchableOpacity disabled={busy} onPress={() => load(true)} accessibilityRole="button">
          <Text style={styles.link}>{busy ? 'Checking…' : 'Refresh'}</Text>
        </TouchableOpacity>
      </View>
      <Text style={styles.note}>Next 14 days · within 50 km of your launch point</Text>
      <Text style={styles.note}>Limited calendar coverage. Events disappear after ending or 24 hours without verification.</Text>
      {error ? <Text style={styles.note}>{error}</Text> : null}
      {!busy && !error && !current.length ? <Text style={styles.empty}>No verified events in this region right now.</Text> : null}
      {(expanded ? current : current.slice(0, 3)).map(event => (
        <EventCard key={`${event.source_id}/${event.occurrence_id}`} event={event}>
          <Text style={styles.date}>{when(event)}</Text>
          <Text style={styles.eventTitle}>{event.title}</Text>
          <Text style={styles.note}>{event.venue_name}</Text>
          <Text style={styles.note}>{event.access_note}</Text>
          <Text style={styles.note}>Source: {event.source_name || 'Organizer'} · checked {new Date(event.verified_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}</Text>
          <TouchableOpacity disabled={checking !== null} onPress={() => open(event)} accessibilityRole="button">
            <Text style={styles.link}>{checking === event.occurrence_id ? 'Checking organizer…' : 'Check event & directions'}</Text>
          </TouchableOpacity>
        </EventCard>
      ))}
      {current.length > 3 ? <TouchableOpacity onPress={() => setExpanded(value => !value)}>
        <Text style={styles.link}>{expanded ? 'Show fewer dates' : `Show all ${current.length} dates`}</Text>
      </TouchableOpacity> : null}
    </View>
  );
};

const styles = StyleSheet.create({
  section: { marginTop: 18, marginBottom: 22, padding: 16, backgroundColor: '#fff', borderRadius: 16 },
  heading: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  title: { fontSize: 20, fontWeight: '800', color: '#163f6b', flex: 1 },
  note: { fontSize: 14, lineHeight: 21, color: '#4b5563', marginTop: 4 },
  empty: { color: '#4b5563', paddingVertical: 14 },
  event: { borderTopWidth: 1, borderTopColor: '#e5e7eb', paddingTop: 14, marginTop: 14 },
  date: { color: '#163f6b', fontSize: 14, fontWeight: '700' },
  eventTitle: { color: '#111827', fontSize: 18, fontWeight: '700', marginTop: 6 },
  link: { color: '#163f6b', fontWeight: '700', paddingVertical: 10 },
});

export default LocalEventsSection;
