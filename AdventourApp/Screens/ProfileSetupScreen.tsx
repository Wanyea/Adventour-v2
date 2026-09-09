import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import AnimatedClouds from '../src/components/AnimatedClouds';
import AuthService, { User } from '../src/services/AuthService';

const wordmark = require('../src/assets/brand/adventour-wordmark.png');
const balloon = require('../src/assets/brand/adventour-balloon.png');

const SKY_BACKGROUND = '#bfeaf4';
const SKY_STROKE = '#87cfe1';
const NAVY = '#123c69';
const ACCENT_ORANGE = '#ff9f1c';
const ACCENT_RED = '#ff4b47';

type ProfileSetupScreenProps = {
  user: User;
  onComplete: (user: User) => void;
};

const onlyDigits = (value: string) => value.replace(/\D/g, '');

const formatBirthdateInput = (value: string) => {
  const digits = onlyDigits(value).slice(0, 8);
  const month = digits.slice(0, 2);
  const day = digits.slice(2, 4);
  const year = digits.slice(4, 8);

  return [month, day, year].filter(Boolean).join('/');
};

const parseBirthdateInput = (value: string) => {
  const digits = onlyDigits(value);
  if (digits.length !== 8) {
    return null;
  }

  const month = Number(digits.slice(0, 2));
  const day = Number(digits.slice(2, 4));
  const year = Number(digits.slice(4, 8));
  const parsed = new Date(year, month - 1, day);
  if (
    parsed.getFullYear() !== year ||
    parsed.getMonth() !== month - 1 ||
    parsed.getDate() !== day
  ) {
    return null;
  }

  return { month, day, year, iso: `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}` };
};

const ageFromBirthdate = (birthdate: { month: number; day: number; year: number }) => {
  const today = new Date();
  let age = today.getFullYear() - birthdate.year;
  const birthdayPassedThisYear =
    today.getMonth() + 1 > birthdate.month ||
    (today.getMonth() + 1 === birthdate.month && today.getDate() >= birthdate.day);
  if (!birthdayPassedThisYear) {
    age -= 1;
  }
  return age;
};

const zodiacFor = (month: number, day: number) => {
  const signs = [
    { name: 'Capricorn', symbol: '♑', from: [1, 1], to: [1, 19] },
    { name: 'Aquarius', symbol: '♒', from: [1, 20], to: [2, 18] },
    { name: 'Pisces', symbol: '♓', from: [2, 19], to: [3, 20] },
    { name: 'Aries', symbol: '♈', from: [3, 21], to: [4, 19] },
    { name: 'Taurus', symbol: '♉', from: [4, 20], to: [5, 20] },
    { name: 'Gemini', symbol: '♊', from: [5, 21], to: [6, 20] },
    { name: 'Cancer', symbol: '♋', from: [6, 21], to: [7, 22] },
    { name: 'Leo', symbol: '♌', from: [7, 23], to: [8, 22] },
    { name: 'Virgo', symbol: '♍', from: [8, 23], to: [9, 22] },
    { name: 'Libra', symbol: '♎', from: [9, 23], to: [10, 22] },
    { name: 'Scorpio', symbol: '♏', from: [10, 23], to: [11, 21] },
    { name: 'Sagittarius', symbol: '♐', from: [11, 22], to: [12, 21] },
    { name: 'Capricorn', symbol: '♑', from: [12, 22], to: [12, 31] },
  ];

  const numericDate = month * 100 + day;
  const sign = signs.find((item) => {
    const from = item.from[0] * 100 + item.from[1];
    const to = item.to[0] * 100 + item.to[1];
    return numericDate >= from && numericDate <= to;
  });

  return sign ? `${sign.symbol} ${sign.name}` : null;
};

const birthdateToInput = (value?: string) => {
  if (!value) {
    return '';
  }
  const [year, month, day] = value.split('-');
  return month && day && year ? `${month}/${day}/${year}` : '';
};

const ProfileSetupScreen: React.FC<ProfileSetupScreenProps> = ({ user, onComplete }) => {
  const [displayName, setDisplayName] = useState(user.display_name || '');
  const [birthdateText, setBirthdateText] = useState(birthdateToInput(user.date_of_birth));
  const [homeCity, setHomeCity] = useState(user.home_city || '');
  const [submitting, setSubmitting] = useState(false);
  const mounted = useRef(true);
  const saveInFlight = useRef(false);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const trimmedDisplayName = displayName.trim();
  const parsedBirthdate = useMemo(() => parseBirthdateInput(birthdateText), [birthdateText]);
  const age = parsedBirthdate ? ageFromBirthdate(parsedBirthdate) : null;
  const zodiac = parsedBirthdate ? zodiacFor(parsedBirthdate.month, parsedBirthdate.day) : null;
  const isOldEnough = age !== null && age >= 13;
  const canContinue = Boolean(trimmedDisplayName) && Boolean(parsedBirthdate) && isOldEnough && !submitting;

  const handleBirthdateChange = (value: string) => {
    setBirthdateText(formatBirthdateInput(value));
  };

  const saveProfile = async () => {
    if (!canContinue || !parsedBirthdate || saveInFlight.current) {
      return;
    }

    saveInFlight.current = true;
    setSubmitting(true);
    try {
      const normalizedHomeCity = homeCity.trim() || null;
      const updatedUser = await AuthService.updateProfile({
        display_name: trimmedDisplayName,
        date_of_birth: parsedBirthdate.iso,
        home_city: normalizedHomeCity,
      });
      if (!mounted.current) {
        return;
      }
      if (updatedUser.id !== user.id || updatedUser.home_city !== normalizedHomeCity) {
        Alert.alert('Setup did not save', 'Your home base was not confirmed. Please try again.');
        return;
      }
      if (!updatedUser.profile_complete && !(updatedUser.display_name && updatedUser.date_of_birth)) {
        Alert.alert(
          'Setup did not save',
          'Adventour saved something unexpected from the backend. Please restart the backend and try again.',
        );
        return;
      }
      onComplete(updatedUser);
    } catch (error: any) {
      if (!mounted.current) {
        return;
      }
      console.error('Profile setup error:', error);
      const message = error?.response?.data?.error || 'Unable to save your passport details. Please try again.';
      Alert.alert('Setup failed', message);
    } finally {
      saveInFlight.current = false;
      if (mounted.current) {
        setSubmitting(false);
      }
    }
  };

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
      <AnimatedClouds height={980} speed="slow" />
      <View style={styles.foreground}>
        <View style={styles.heroCard}>
          <Image source={wordmark} style={styles.wordmark} resizeMode="contain" />
          <Text style={styles.kicker}>Passport details</Text>
          <Text style={styles.title}>Who is launching this Adventour?</Text>
          <Text style={styles.subtitle}>
            Confirm your display name and birthday before we stamp your first travel moods.
          </Text>
          <Image source={balloon} style={styles.balloon} resizeMode="contain" />
        </View>

        <View style={styles.formCard}>
          <Text style={styles.label}>Display name</Text>
          <TextInput
            style={styles.input}
            placeholder="Your Adventour name"
            value={displayName}
            onChangeText={setDisplayName}
            autoCapitalize="words"
            autoCorrect={false}
            maxLength={40}
            editable={!submitting}
          />
          {!trimmedDisplayName ? (
            <Text style={styles.validationText}>Choose a display name for your passport.</Text>
          ) : null}

          <Text style={styles.label}>Birthdate</Text>
          <View style={styles.birthdateRow}>
            <TextInput
              style={[styles.input, styles.birthdateInput]}
              placeholder="MM/DD/YYYY"
              value={birthdateText}
              onChangeText={handleBirthdateChange}
              keyboardType="number-pad"
              maxLength={10}
              editable={!submitting}
            />
            {zodiac ? (
              <View style={styles.zodiacPill}>
                <Text style={styles.zodiacText}>{zodiac}</Text>
              </View>
            ) : null}
          </View>
          {birthdateText.length > 0 && !parsedBirthdate ? (
            <Text style={styles.validationText}>Enter a real birthdate as MM/DD/YYYY.</Text>
          ) : null}
          {parsedBirthdate && !isOldEnough ? (
            <Text style={styles.validationText}>Adventour accounts are for travelers age 13 and up.</Text>
          ) : null}
          {parsedBirthdate && isOldEnough ? (
            <Text style={styles.helperText}>Looks good. Age check passed.</Text>
          ) : null}

          <Text style={styles.label}>Home city or town</Text>
          <TextInput
            style={styles.input}
            placeholder="City or town, region, country"
            value={homeCity}
            onChangeText={setHomeCity}
            autoCapitalize="words"
            autoCorrect={false}
            maxLength={160}
            editable={!submitting}
          />
          <Text style={styles.helperText}>Optional. Add a region or country when useful; no street address needed.</Text>

          <TouchableOpacity
            style={[styles.button, !canContinue && styles.buttonDisabled]}
            onPress={saveProfile}
            disabled={!canContinue}
            activeOpacity={0.86}
          >
            {submitting ? (
              <ActivityIndicator color="#fffaf3" />
            ) : (
              <Text style={styles.buttonText}>Continue to travel moods</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: SKY_BACKGROUND,
  },
  content: {
    flexGrow: 1,
    backgroundColor: SKY_BACKGROUND,
    overflow: 'hidden',
    padding: 18,
    paddingBottom: 30,
    position: 'relative',
  },
  foreground: {
    flex: 1,
    justifyContent: 'center',
    zIndex: 1,
  },
  heroCard: {
    backgroundColor: '#d9f8fb',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 245,
    overflow: 'hidden',
    padding: 18,
    shadowColor: NAVY,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  wordmark: {
    height: 75,
    marginBottom: -18,
    marginLeft: -4,
    marginTop: -18,
    width: 145,
  },
  kicker: {
    color: ACCENT_RED,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.7,
    marginTop: 10,
    textTransform: 'uppercase',
  },
  title: {
    color: NAVY,
    fontSize: 27,
    fontWeight: '900',
    lineHeight: 31,
    marginTop: 8,
    paddingRight: 112,
  },
  subtitle: {
    color: '#31506b',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 10,
    paddingRight: 105,
  },
  balloon: {
    bottom: 10,
    height: 150,
    position: 'absolute',
    right: 18,
    width: 108,
  },
  formCard: {
    backgroundColor: '#fffaf3',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 14,
    padding: 16,
  },
  label: {
    color: NAVY,
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 7,
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#ffffff',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    color: NAVY,
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
    paddingHorizontal: 14,
    paddingVertical: 13,
  },
  birthdateRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
  },
  birthdateInput: {
    flex: 1,
  },
  zodiacPill: {
    backgroundColor: '#dff6f2',
    borderColor: ACCENT_ORANGE,
    borderRadius: 999,
    borderWidth: 2,
    marginBottom: 12,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  zodiacText: {
    color: NAVY,
    fontSize: 12,
    fontWeight: '900',
  },
  validationText: {
    color: '#9f1239',
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 12,
    marginTop: -6,
  },
  helperText: {
    color: '#0f766e',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 12,
    marginTop: -5,
  },
  button: {
    alignItems: 'center',
    backgroundColor: NAVY,
    borderColor: ACCENT_ORANGE,
    borderRadius: 999,
    borderWidth: 2,
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  buttonDisabled: {
    backgroundColor: '#7aa6bd',
    borderColor: '#9ad8e8',
    opacity: 0.72,
  },
  buttonText: {
    color: '#fffaf3',
    fontSize: 15,
    fontWeight: '900',
  },
});

export default ProfileSetupScreen;
