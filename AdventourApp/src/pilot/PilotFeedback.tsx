import React, { useEffect, useRef, useState } from 'react';
import { AppState, Dimensions, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { useIsFocused } from '@react-navigation/native';
import { v4 as uuid } from 'uuid';
import Config from '../Config';
import { tagGroupDisplayLabel } from '../placeTagGroups';
import { Invitation, pilotPost, signalPilot, submitPilot } from './PilotService';

const reasons = [
  ['taste', 'Not my kind of activity'], ['setting', 'Wrong atmosphere or format'],
  ['distance', 'Too far'], ['timing', 'Wrong time'], ['price_booking', 'Cost or booking'],
  ['familiar', 'Already know it'], ['unclear', 'Not enough information'],
  ['facts', 'Something looks wrong'], ['other', 'Something else'],
];
type Props = { decisionId?: string; title: string; cardRef?: React.RefObject<View | null>; active?: boolean };

// The outer gate also prevents hooks, storage and network work in standard builds.
export default function PilotFeedback(props: Props) {
  return Config.PILOT_BUILD && props.decisionId ? <Feedback key={props.decisionId} {...props} decisionId={props.decisionId} /> : null;
}

function Feedback({ decisionId, title, cardRef, active = true }: Props & { decisionId: string }) {
  const focused = useIsFocused();
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [value, setValue] = useState<number | null | undefined>();
  const [reason, setReason] = useState<string>();
  const [problem, setProblem] = useState<string>();
  const [note, setNote] = useState('');
  const [more, setMore] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  const started = useRef(0);
  const panelRef = useRef<View>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  const show = (inv: Invitation | null) => {
    if (alive.current && inv?.status === 'offered') {
      started.current = Date.now(); setInvitation(inv);
    }
  };
  useEffect(() => {
    if (!invitation || !focused || !foreground || !active) { return; }
    let sent = false;
    const timer = setInterval(() => panelRef.current?.measureInWindow((_x, y, _w, height) => {
      if (sent || height <= 0 || y < 0 || y >= Dimensions.get('window').height - 40) { return; }
      sent = true;
      pilotPost(decisionId, 'present', { invitation_id: invitation.id }).catch(() => { sent = false; });
    }), 250);
    return () => clearInterval(timer);
  }, [invitation, decisionId, focused, foreground, active]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => {
      setForeground(state === 'active');
    });
    return () => subscription.remove();
  }, []);
  useEffect(() => {
    if (!cardRef || !focused || !foreground || !active) { return; }
    let since = 0, sent = false, stopped = false;
    const timer = setInterval(() => {
      if (sent) { return; }
      cardRef.current?.measureInWindow((_x, y, _width, height) => {
        if (stopped) { return; }
        const visible = Math.max(0, Math.min(y + height, Dimensions.get('window').height) - Math.max(y, 0));
        if (height <= 0 || visible < height / 2) { since = 0; return; }
        if (!since) { since = Date.now(); }
        if (Date.now() - since >= 1000) {
          sent = true;
          signalPilot(decisionId, 'view', Date.now() - since)
            .then(result => { if (!stopped) { show(result.invitation); } })
            .catch(() => { sent = false; });
        }
      });
    }, 250);
    return () => { stopped = true; clearInterval(timer); };
  }, [cardRef, decisionId, focused, foreground, active]);

  const open = async () => {
    setBusy(true); setMessage('');
    try { const result = await pilotPost(decisionId, 'invite', {}); show(result.invitation);
      if (result.invitation?.status !== 'offered') { setMessage('Feedback already recorded for this card.'); }
    } catch { setMessage('Could not open feedback. Try again.'); }
    finally { if (alive.current) { setBusy(false); } }
  };
  const save = async (skip = false) => {
    if (!invitation || busy || (!skip && value === undefined)) { return; }
    setBusy(true);
    const data = skip ? { invitation_id: invitation.id } : {
      id: uuid(), invitation_id: invitation.id, answer_kind: value === null ? 'unknown' : 'rated',
      value, reason, problem: reason === 'facts' ? problem : undefined,
      note: note || undefined, duration_ms: Math.min(86400000, Date.now() - started.current),
      occurred_at: new Date().toISOString(),
    };
    try {
      const status = await submitPilot(decisionId, skip ? 'skip' : 'feedback', data);
      if (alive.current) {
        setInvitation(null);
        setMessage(status === 'saved' ? (skip ? 'Skipped' : 'Thanks, saved') :
          status === 'pending' ? 'Saved on this phone. Waiting to upload.' : 'Feedback could not be accepted.');
      }
    } catch { if (alive.current) { setMessage('Could not save on this phone. Try again.'); } }
    finally { if (alive.current) { setBusy(false); } }
  };
  if (!invitation) {
    return <View><TouchableOpacity disabled={busy} onPress={open} accessibilityRole="button">
      <Text style={styles.link}>{busy ? 'Opening…' : 'Feedback (optional)'}</Text>
    </TouchableOpacity>{message ? <Text style={styles.note}>{message}</Text> : null}</View>;
  }
  const relevance = invitation.question === 'relevance_v1';
  const labels = relevance ? ['Not at all', 'Slightly', 'Moderately', 'Very well', 'Extremely well'] :
    ['Not at all', 'Slightly', 'Moderately', 'Very', 'Extremely'];
  return <View ref={panelRef} style={styles.panel}>
    <Text style={styles.title}>{relevance ? `How well does ${title} match your interest in ${tagGroupDisplayLabel(invitation.interest || '')}?` : `How appealing is ${title} to you?`}</Text>
    <View style={styles.choices}>{[...labels, "Can't tell"].map((label, index) => {
      const answer = index === 5 ? null : index;
      return <TouchableOpacity key={label} disabled={busy} accessibilityRole="radio"
        accessibilityState={{ checked: value === answer }} onPress={() => setValue(answer)}
        style={[styles.choice, value === answer && styles.selected]}><Text>{label}</Text></TouchableOpacity>;
    })}</View>
    <TouchableOpacity onPress={() => setMore(!more)}><Text style={styles.link}>Add a reason or note (optional)</Text></TouchableOpacity>
    {more ? <View><Text style={styles.note}>What was the main reason?</Text>
      <View style={styles.choices}>{reasons.map(([key, label]) => <TouchableOpacity key={key}
        onPress={() => setReason(reason === key ? undefined : key)} style={[styles.choice, reason === key && styles.selected]}>
        <Text>{label}</Text></TouchableOpacity>)}</View>
      {reason === 'facts' ? <View style={styles.choices}>{[
        ['location', 'Location'], ['date_time', 'Date or time'], ['closed_cancelled', 'Closed or cancelled'],
        ['sold_out_access', 'Sold out or restricted'], ['broken_link', 'Broken link'],
        ['category_description', 'Description'], ['other', 'Other'],
      ].map(([key, label]) => <TouchableOpacity key={key} onPress={() => setProblem(problem === key ? undefined : key)}
        style={[styles.choice, problem === key && styles.selected]}><Text>{label}</Text></TouchableOpacity>)}</View> : null}
      <TextInput value={note} onChangeText={setNote} maxLength={280} multiline placeholder="Anything else? (optional)"
        accessibilityLabel="Optional feedback note" style={styles.input} /></View> : null}
    <View style={styles.choices}><TouchableOpacity disabled={busy || value === undefined} onPress={() => save()}>
      <Text style={[styles.link, value === undefined && styles.disabled]}>{busy ? 'Saving…' : 'Send'}</Text>
    </TouchableOpacity><TouchableOpacity disabled={busy} onPress={() => save(true)}><Text style={styles.link}>Skip</Text></TouchableOpacity></View>
    {message ? <Text style={styles.note}>{message}</Text> : null}
  </View>;
}

const styles = StyleSheet.create({
  panel: { paddingTop: 10, borderTopWidth: 1, borderTopColor: '#e5e7eb' },
  title: { fontSize: 15, fontWeight: '700', color: '#163f6b' },
  choices: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  choice: { padding: 10, borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, backgroundColor: '#fff' },
  selected: { borderColor: '#163f6b', backgroundColor: '#dff6f2' },
  link: { paddingVertical: 10, paddingRight: 16, color: '#163f6b', fontWeight: '700' },
  disabled: { opacity: 0.4 }, note: { color: '#4b5563', fontSize: 13 },
  input: { borderWidth: 1, borderColor: '#e5e7eb', borderRadius: 8, padding: 10, marginTop: 8, color: '#111827' },
});
