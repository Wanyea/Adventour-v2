import React, { ReactNode, useEffect, useRef, useState } from 'react';
import {
  Keyboard,
  StyleProp,
  StyleSheet,
  Text,
  TextInput,
  TextInputProps,
  TextStyle,
  TouchableOpacity,
  View,
} from 'react-native';
import LaunchLocationService, { LaunchSuggestion } from '../LaunchLocationService';

type LocationAutocompleteInputProps = Omit<TextInputProps, 'value' | 'onChangeText' | 'style'> & {
  value: string;
  onChangeText: (value: string) => void;
  onSelectSuggestion: (suggestion: LaunchSuggestion) => void;
  inputStyle?: StyleProp<TextStyle>;
  trailingContent?: ReactNode;
  onSearchError?: (message: string) => void;
};

const LOCATION_KIND_PATTERN = /^(.*)\s+\((City|Town|Village|Hamlet|Neighborhood|State|Country|District|Locality|County|Street)\)$/;

export const splitLocationDescription = (description: string) => {
  const match = description.match(LOCATION_KIND_PATTERN);
  return match ? { place: match[1], kind: match[2] } : { place: description, kind: null };
};

const LocationAutocompleteInput: React.FC<LocationAutocompleteInputProps> = ({
  value,
  onChangeText,
  onSelectSuggestion,
  inputStyle,
  trailingContent,
  onSearchError,
  editable = true,
  placeholder = 'City or town, region, country',
  ...textInputProps
}) => {
  const [suggestions, setSuggestions] = useState<LaunchSuggestion[]>([]);
  const requestVersion = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const suggestionCache = useRef(new Map<string, LaunchSuggestion[]>());

  useEffect(() => () => {
    if (timer.current) {
      clearTimeout(timer.current);
    }
  }, []);

  const handleChange = (text: string) => {
    onChangeText(text);
    const version = ++requestVersion.current;
    const normalizedInput = text.trim();
    if (timer.current) {
      clearTimeout(timer.current);
    }
    if (normalizedInput.length < 3) {
      setSuggestions([]);
      onSearchError?.('');
      return;
    }

    const cachedMatches = suggestionCache.current.get(normalizedInput.toLowerCase());
    if (cachedMatches) {
      setSuggestions(cachedMatches);
      onSearchError?.(cachedMatches.length ? '' : 'No matching location found. Try a more specific city or town.');
      return;
    }

    timer.current = setTimeout(async () => {
      try {
        const matches = await LaunchLocationService.fetchAutocompleteSuggestions(normalizedInput);
        if (version !== requestVersion.current) return;
        suggestionCache.current.set(normalizedInput.toLowerCase(), matches);
        setSuggestions(matches);
        onSearchError?.(matches.length ? '' : 'No matching location found. Try a more specific city or town.');
      } catch {
        if (version !== requestVersion.current) return;
        setSuggestions([]);
        onSearchError?.('Location search is temporarily unavailable. Try again later.');
      }
    }, 300);
  };

  const handleSelect = (suggestion: LaunchSuggestion) => {
    requestVersion.current += 1;
    if (timer.current) {
      clearTimeout(timer.current);
    }
    Keyboard.dismiss();
    setSuggestions([]);
    onSearchError?.('');
    const { place } = splitLocationDescription(suggestion.description);
    onSelectSuggestion({ ...suggestion, description: place });
  };

  return (
    <View style={styles.wrapper}>
      <View style={styles.inputRow}>
        <TextInput
          {...textInputProps}
          style={inputStyle}
          placeholder={placeholder}
          value={value}
          onChangeText={handleChange}
          editable={editable}
        />
        {trailingContent}
      </View>
      {suggestions.length > 0 ? (
        <View style={styles.suggestionsList}>
          {suggestions.map((suggestion) => (
            <TouchableOpacity
              key={suggestion.suggestion_id}
              style={styles.suggestionItem}
              onPress={() => handleSelect(suggestion)}
              disabled={!editable}
            >
              <Text style={styles.suggestionText}>
                {splitLocationDescription(suggestion.description).place}
                {splitLocationDescription(suggestion.description).kind ? (
                  <Text style={styles.suggestionKind}> ({splitLocationDescription(suggestion.description).kind})</Text>
                ) : null}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      ) : null}
    </View>
  );
};

const styles = StyleSheet.create({
  wrapper: { flex: 1 },
  inputRow: { alignItems: 'center', flexDirection: 'row' },
  suggestionsList: {
    backgroundColor: '#fffaf3',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 6,
    overflow: 'hidden',
  },
  suggestionItem: { borderBottomColor: '#d8edf2', borderBottomWidth: 1, paddingHorizontal: 12, paddingVertical: 10 },
  suggestionText: { color: '#123c69', fontSize: 13 },
  suggestionKind: { color: '#6b7280', fontSize: 12, fontWeight: '800' },
});

export default LocationAutocompleteInput;
