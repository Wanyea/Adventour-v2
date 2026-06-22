import React, { useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import axios from 'axios';
import Config from '../src/Config';
import AnimatedClouds from '../src/components/AnimatedClouds';
import { TAG_GROUPS } from '../src/placeTagGroups';

interface OnboardingScreenProps {
  onComplete: () => void;
}

const wordmark = require('../src/assets/brand/adventour-wordmark.png');
const balloon = require('../src/assets/brand/adventour-balloon.png');

const SKY_BACKGROUND = '#bfeaf4';
const SKY_STROKE = '#87cfe1';
const NAVY = '#123c69';
const ACCENT_ORANGE = '#ff9f1c';
const ACCENT_RED = '#ff4b47';

const OnboardingScreen: React.FC<OnboardingScreenProps> = ({ onComplete }) => {
  const [selectedTagGroups, setSelectedTagGroups] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const selectedCountText = useMemo(() => {
    if (!selectedTagGroups.length) {
      return 'Pick a few travel moods';
    }

    return `${selectedTagGroups.length} selected`;
  }, [selectedTagGroups.length]);

  const toggleTagGroup = (tagGroupId: string) => {
    setSelectedTagGroups((current) => (
      current.includes(tagGroupId)
        ? current.filter((tag) => tag !== tagGroupId)
        : [...current, tagGroupId]
    ));
  };

  const submitOnboarding = async () => {
    if (selectedTagGroups.length === 0) {
      Alert.alert('Pick at least one tag group', 'This gives Adventour a starting point before your swipes teach it more.');
      return;
    }

    setSubmitting(true);
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/onboarding`, {
        initial_tags: selectedTagGroups,
        initial_tag_groups: selectedTagGroups,
      });
      onComplete();
    } catch (error) {
      console.error('Error submitting onboarding:', error);
      Alert.alert('Unable to save preferences', 'Please try again in a moment.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      showsVerticalScrollIndicator={false}
    >
      <AnimatedClouds height={1320} speed="slow" />
      <View style={styles.foreground}>
        <View style={styles.heroCard}>
          <Image source={wordmark} style={styles.wordmark} resizeMode="contain" />
          <View style={styles.heroText}>
            <Text style={styles.kicker}>Passport setup</Text>
            <Text style={styles.title}>What kind of Adventour should we launch first?</Text>
            <Text style={styles.subtitle}>
              Choose the tag groups that sound most like you. Your swipes will take over from here.
            </Text>
          </View>
          <Image source={balloon} style={styles.balloon} resizeMode="contain" />
        </View>

        <View style={styles.statusPill}>
          <Text style={styles.statusPillText}>{selectedCountText}</Text>
        </View>

        <View style={styles.tagGrid}>
          {TAG_GROUPS.map((group) => {
            const selected = selectedTagGroups.includes(group.id);
            return (
              <TouchableOpacity
                key={group.id}
                activeOpacity={0.82}
                onPress={() => toggleTagGroup(group.id)}
                style={[
                  styles.tagCard,
                  {
                    borderColor: selected ? group.color : SKY_STROKE,
                    backgroundColor: selected ? group.backgroundColor : '#e8fbff',
                  },
                  selected && styles.tagCardSelected,
                ]}
              >
                <View style={styles.tagCardHeader}>
                  <Text style={styles.tagEmoji}>{group.emoji}</Text>
                  <View style={[
                    styles.checkDot,
                    selected && { backgroundColor: group.color, borderColor: group.color },
                  ]}>
                    <Text style={styles.checkText}>{selected ? '✓' : ''}</Text>
                  </View>
                </View>
                <Text style={[styles.tagTitle, { color: group.color }]}>{group.label}</Text>
                <Text style={styles.tagDescription} numberOfLines={3}>{group.description}</Text>
              </TouchableOpacity>
            );
          })}
        </View>

        <TouchableOpacity
          style={[
            styles.submitButton,
            (!selectedTagGroups.length || submitting) && styles.submitButtonDisabled,
          ]}
          onPress={submitOnboarding}
          disabled={!selectedTagGroups.length || submitting}
          activeOpacity={0.86}
        >
          {submitting ? (
            <ActivityIndicator color="#fffaf3" />
          ) : (
            <Text style={styles.submitButtonText}>Stamp my passport</Text>
          )}
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: SKY_BACKGROUND,
  },
  content: {
    overflow: 'hidden',
    padding: 18,
    paddingBottom: 30,
    position: 'relative',
  },
  foreground: {
    zIndex: 1,
  },
  heroCard: {
    minHeight: 265,
    backgroundColor: '#d9f8fb',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    overflow: 'hidden',
    padding: 18,
    shadowColor: NAVY,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  wordmark: {
    width: 145,
    height: 80,
    marginLeft: -4,
    marginBottom: -20,
    marginTop: -20,
    zIndex: 1,
  },
  heroText: {
    marginTop: 12,
    paddingRight: 100,
    zIndex: 1,
  },
  kicker: {
    color: ACCENT_RED,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.7,
    marginBottom: 7,
    textTransform: 'uppercase',
  },
  title: {
    color: NAVY,
    fontSize: 27,
    fontWeight: '900',
    lineHeight: 31,
  },
  subtitle: {
    color: '#31506b',
    fontSize: 14,
    fontWeight: '700',
    lineHeight: 20,
    marginTop: 10,
  },
  balloon: {
    position: 'absolute',
    bottom: 8,
    right: 16,
    width: 112,
    height: 156,
    zIndex: 1,
  },
  statusPill: {
    alignSelf: 'flex-start',
    backgroundColor: NAVY,
    borderColor: ACCENT_ORANGE,
    borderRadius: 999,
    borderWidth: 2,
    marginTop: 14,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  statusPillText: {
    color: '#fffaf3',
    fontSize: 13,
    fontWeight: '900',
  },
  tagGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginTop: 14,
  },
  tagCard: {
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 142,
    padding: 12,
    width: '48.5%',
  },
  tagCardSelected: {
    borderWidth: 2,
    shadowColor: NAVY,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 5,
    elevation: 2,
  },
  tagCardHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  tagEmoji: {
    fontSize: 24,
  },
  checkDot: {
    alignItems: 'center',
    borderColor: SKY_STROKE,
    borderRadius: 999,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    width: 24,
  },
  checkText: {
    color: '#fffaf3',
    fontSize: 14,
    fontWeight: '900',
  },
  tagTitle: {
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 18,
  },
  tagDescription: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 16,
    marginTop: 6,
  },
  submitButton: {
    alignItems: 'center',
    backgroundColor: NAVY,
    borderColor: ACCENT_ORANGE,
    borderRadius: 999,
    borderWidth: 2,
    marginTop: 20,
    paddingVertical: 15,
    shadowColor: NAVY,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.18,
    shadowRadius: 7,
    elevation: 3,
  },
  submitButtonDisabled: {
    opacity: 0.58,
  },
  submitButtonText: {
    color: '#fffaf3',
    fontSize: 16,
    fontWeight: '900',
  },
});

export default OnboardingScreen;
