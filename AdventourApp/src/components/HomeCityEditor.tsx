import React, { useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import AuthService, { User } from '../services/AuthService';
import LocationAutocompleteInput from './LocationAutocompleteInput';

type HomeCityEditorProps = {
  userId: number;
  homeCity?: string | null;
  onUserUpdated?: (user: User) => void;
};

export const normalizedHomeCity = (value: string) => value.trim() || null;

const HomeCityEditor: React.FC<HomeCityEditorProps> = ({ userId, homeCity, onUserUpdated }) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(homeCity || '');
  const [saving, setSaving] = useState(false);
  const mounted = useRef(true);
  const saveInFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    if (!editing) {
      setDraft(homeCity || '');
    }
  }, [editing, homeCity]);

  const cancel = () => {
    setDraft(homeCity || '');
    setEditing(false);
  };

  const save = async () => {
    if (saveInFlight.current) {
      return;
    }
    saveInFlight.current = true;
    const requestedHomeCity = normalizedHomeCity(draft);
    setSaving(true);
    try {
      const updatedUser = await AuthService.updateProfile({ home_city: requestedHomeCity });
      if (updatedUser.id !== userId || updatedUser.home_city !== requestedHomeCity) {
        throw new Error('The server did not confirm this home base for the active account.');
      }
      if (!mounted.current) {
        return;
      }
      onUserUpdated?.(updatedUser);
      setEditing(false);
    } catch (error) {
      if (!mounted.current) {
        return;
      }
      console.error('Error saving home city:', error);
      Alert.alert('Unable to save home base', 'Your home city or town could not be saved. Please try again.');
    } finally {
      saveInFlight.current = false;
      if (mounted.current) {
        setSaving(false);
      }
    }
  };

  return (
    <View style={styles.card}>
      <View style={styles.headingRow}>
        <View style={styles.headingText}>
          <Text style={styles.title}>Home base</Text>
          <Text style={styles.helper}>Your own city or town. Add a region or country when useful; no street address needed.</Text>
        </View>
        {!editing ? (
          <TouchableOpacity onPress={() => setEditing(true)} accessibilityLabel="Edit home base">
            <Text style={styles.edit}>Edit</Text>
          </TouchableOpacity>
        ) : null}
      </View>
      {editing ? (
        <>
          <LocationAutocompleteInput
            inputStyle={styles.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="City or town, region, country"
            autoCapitalize="words"
            autoCorrect={false}
            maxLength={160}
            editable={!saving}
            accessibilityLabel="Home city or town"
            onSelectSuggestion={(suggestion) => setDraft(suggestion.description)}
          />
          <View style={styles.actions}>
            <TouchableOpacity onPress={() => setDraft('')} disabled={saving}>
              <Text style={styles.clear}>Clear</Text>
            </TouchableOpacity>
            <View style={styles.rightActions}>
              <TouchableOpacity onPress={cancel} disabled={saving}>
                <Text style={styles.cancel}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.saveButton} onPress={save} disabled={saving}>
                {saving ? <ActivityIndicator color="#fffaf3" /> : <Text style={styles.save}>Save</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </>
      ) : (
        <Text style={styles.value}>{homeCity || 'Not set'}</Text>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  card: { marginBottom: 18 },
  headingRow: { alignItems: 'flex-start', flexDirection: 'row', gap: 12, justifyContent: 'space-between' },
  headingText: { flex: 1, flexShrink: 1 },
  title: { color: '#123c69', fontSize: 12, fontWeight: '900', textTransform: 'uppercase' },
  helper: { color: '#6b7280', fontSize: 12, marginTop: 3 },
  edit: { color: '#e6534b', fontWeight: '800' },
  value: { color: '#123c69', fontSize: 16, fontWeight: '800', marginTop: 7 },
  input: { backgroundColor: '#fff', borderColor: '#87cfe1', borderRadius: 8, borderWidth: 1, color: '#123c69', marginTop: 10, paddingHorizontal: 12, paddingVertical: 9 },
  actions: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 },
  rightActions: { alignItems: 'center', flexDirection: 'row', gap: 14 },
  clear: { color: '#e6534b', fontWeight: '800' },
  cancel: { color: '#123c69', fontWeight: '800' },
  saveButton: { backgroundColor: '#123c69', borderRadius: 8, minWidth: 58, paddingHorizontal: 13, paddingVertical: 8 },
  save: { color: '#fffaf3', fontWeight: '900', textAlign: 'center' },
});

export default HomeCityEditor;
