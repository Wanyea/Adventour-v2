import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Alert } from 'react-native';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Config from '../src/Config';

interface OnboardingScreenProps {
  onComplete: () => void;
}

const OnboardingScreen: React.FC<OnboardingScreenProps> = ({ onComplete }) => {
  const availableTags = ['cafe', 'restaurant', 'museum', 'park', 'theater'];
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);

  useEffect(() => {
    const loadUserId = async () => {
      const storedId = await AsyncStorage.getItem('user_id');
      setUserId(storedId);
    };
    loadUserId();
  }, []);

  const toggleTag = (tag: string) => {
    if (selectedTags.includes(tag)) {
      setSelectedTags(selectedTags.filter(t => t !== tag));
    } else {
      setSelectedTags([...selectedTags, tag]);
    }
  };

  const submitOnboarding = async () => {
    if (!userId) {
      Alert.alert("Error", "User ID is missing.");
      return;
    }

    if (selectedTags.length === 0) {
      Alert.alert("Please select at least one preference.");
      return;
    }

    try {
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/onboarding`, {
        user_id: userId,
        initial_tags: selectedTags,
      });
      console.log("Onboarding response:", response.data);
      onComplete();
    } catch (error) {
      console.error("Error submitting onboarding:", error);
      Alert.alert("Error", "Failed to submit preferences.");
    }
  };

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Select Your Preferences</Text>
      <View style={styles.tagsContainer}>
        {availableTags.map(tag => (
          <TouchableOpacity
            key={tag}
            onPress={() => toggleTag(tag)}
            style={[styles.tagButton, selectedTags.includes(tag) && styles.tagButtonSelected]}
          >
            <Text style={[styles.tagText, selectedTags.includes(tag) && styles.tagTextSelected]}>{tag}</Text>
          </TouchableOpacity>
        ))}
      </View>
      <TouchableOpacity style={styles.submitButton} onPress={submitOnboarding}>
        <Text style={styles.submitButtonText}>Submit Preferences</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 20 },
  title: { fontSize: 24, marginBottom: 20 },
  tagsContainer: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'center' },
  tagButton: { padding: 10, margin: 5, borderWidth: 1, borderColor: '#aaa', borderRadius: 5 },
  tagButtonSelected: { backgroundColor: '#007bff' },
  tagText: { fontSize: 16 },
  tagTextSelected: { color: '#fff' },
  submitButton: { marginTop: 20, backgroundColor: '#28a745', padding: 10, borderRadius: 5 },
  submitButtonText: { color: '#fff', fontSize: 18 },
});

export default OnboardingScreen;
