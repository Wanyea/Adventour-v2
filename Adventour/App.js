import React, { useState } from 'react';
import { View, Text } from 'react-native';
import TagSelection from './src/TagSelection';
import PlaceList from './src/PlaceList';
import { fetchPlaces } from './src/api';
import * as Location from 'expo-location';

const App = () => {
  const [places, setPlaces] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleTagSubmit = async (selectedTags) => {
    setLoading(true);

    // Get the user's current location
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      console.error('Permission to access location was denied');
      setLoading(false);
      return;
    }

    const location = await Location.getCurrentPositionAsync({});
    const fetchedPlaces = await fetchPlaces(selectedTags, location.coords);
    setPlaces(fetchedPlaces);
    setLoading(false);
  };

  return (
    <View style={{ flex: 1, padding: 20 }}>
      <TagSelection onSubmit={handleTagSubmit} />
      {loading ? <Text>Loading...</Text> : <PlaceList places={places} />}
    </View>
  );
};

export default App;
