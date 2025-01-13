import React, { useState, useCallback } from 'react';
import { View, Text, Alert } from 'react-native';
import TagSelection from '../src/TagSelection';
import PlaceList from '../src/PlaceList';
import { fetchPlaces } from '../src/GoogleAPI';
import * as Location from 'expo-location';

const Index = () => {
  const [places, setPlaces] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [userFeedback, setUserFeedback] = useState<any[]>([]);

  const handleTagSubmit = async (selectedTags: string[]) => {
    setLoading(true);

    try {
      // Request location permissions
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission to access location was denied');
        setLoading(false);
        return;
      }

      // Get the user's current location
      const location = await Location.getCurrentPositionAsync({});
      console.log("User Location:", location.coords);

      // Fetch places using Google Places API
      const fetchedPlaces = await fetchPlaces(selectedTags, location.coords);
      console.log("Fetched Places:", fetchedPlaces);

      setPlaces(fetchedPlaces); // Update state with fetched places
    } catch (error) {
      console.error('Error fetching location or places:', error);
      Alert.alert('Error fetching data');
    }

    setLoading(false);
  };

  // Memoized function to handle feedback
  const handleFeedback = useCallback((place: any, feedback: string) => {
    console.log(`User ${feedback}:`, place);
    setUserFeedback((prev) => [
      ...prev,
      { place_id: place.place_id, feedback, tags: place.types },
    ]);
  }, []);

  return (
    <View style={{ flex: 1, padding: 20 }}>
      <TagSelection onSubmit={handleTagSubmit} />
      {loading ? (
        <Text>Loading...</Text>
      ) : places.length > 0 ? (
        <PlaceList places={places} onFeedback={handleFeedback} />
      ) : (
        <Text>No places found...</Text>
      )}
    </View>
  );
};

export default Index;
