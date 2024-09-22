import React, { useState } from 'react';
import { View, Text, Alert } from 'react-native';
import TagSelection from '../src/TagSelection'; // Adjust the path if needed
import PlaceList from '../src/PlaceList'; // Adjust the path if needed
import { fetchPlaces } from '../src/GoogleAPI'; // Update to the new file name
import * as Location from 'expo-location';

const Index = () => {
  const [places, setPlaces] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const handleTagSubmit = async (selectedTags: string[]) => {
    setLoading(true);

    try {
      // Check for location permissions
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission to access location was denied');
        setLoading(false);
        return;
      }

      // Get the current location
      const location = await Location.getCurrentPositionAsync({});
      console.log("User Location:", location.coords);

      // Fetch places using the API
      const fetchedPlaces = await fetchPlaces(selectedTags, location.coords);
      console.log("Fetched Places:", fetchedPlaces);

      setPlaces(fetchedPlaces); // Update state with fetched places
    } catch (error) {
      console.error('Error fetching location or places:', error);
      Alert.alert('Error fetching data');
    }

    setLoading(false);
  };

  return (
    <View style={{ flex: 1, padding: 20 }}>
      <TagSelection onSubmit={handleTagSubmit} />
      {loading ? <Text>Loading...</Text> : places.length > 0 ? (
        <PlaceList places={places} />
      ) : (
        <Text>No places found.</Text>
      )}
    </View>
  );
};

export default Index;
