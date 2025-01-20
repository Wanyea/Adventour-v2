import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  Alert,
  TouchableOpacity,
  StyleSheet,
  Image,
  FlatList,
} from 'react-native';
import TagSelection from '../src/TagSelection';
import PlaceList from '../src/PlaceList';
import GoogleAutocompleteService from '../src/GoogleAutocompleteService'; 
import * as Location from 'expo-location';
import axios from 'axios';

type Place = {
  place_id: string;
  name: string;
  vicinity: string;
  types: string[];
};

const Index = () => {
  const backendBaseURL = 'http://192.168.0.18:5005';
  //  const backendBaseURL = 'https://adventour-73dfb.ue.r.appspot.com';
  const [places, setPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [userFeedback, setUserFeedback] = useState<{ place_id: string; feedback: string; tags: string[] }[]>([]);
  const [userId, setUserId] = useState<string>('test_user'); // Default user ID
  const [city, setCity] = useState<string>(''); // State for city
  const [currentCoords, setCurrentCoords] = useState<{ latitude: number; longitude: number } | null>(null);
  const [suggestions, setSuggestions] = useState<any[]>([]); // State for autocomplete suggestions

  const handleFeedback = async (place: Place, feedback: string) => {
    setUserFeedback((prev) => [
      ...prev,
      { place_id: place.place_id, feedback, tags: place.types },
    ]);
    try {
      const response = await axios.post(`${backendBaseURL}/feedback`, {
        user_id: userId,
        place_id: place.place_id,
        feedback,
        tags: place.types,
      });
      console.log(response.data);
    } catch (error) {
      console.error('Error saving feedback:', error);
    }
  };

  const fetchSuggestions = async (input: string) => {
    if (input.length > 2) {
      const location = currentCoords || { latitude: 0, longitude: 0 }; // Default to global search if no specific location
      const autocompleteSuggestions = await GoogleAutocompleteService.fetchAutocompleteSuggestions(input, location);
      setSuggestions(autocompleteSuggestions);
    }
  };

  const fetchRecommendations = async () => {
    if (!userId) {
      Alert.alert('Error', 'User ID is required.');
      return;
    }

    try {
      const params: any = { user_id: userId };
      if (currentCoords) {
        params.latitude = currentCoords.latitude;
        params.longitude = currentCoords.longitude;
      } else if (city) {
        params.address = city;
      } else {
        Alert.alert('Error', 'Please provide a location.');
        return;
      }

      const response = await axios.get(`${backendBaseURL}/recommendations`, { params });
      setPlaces(response.data); // Update places with recommendations
      Alert.alert('Recommendations loaded!', 'Displaying recommended places based on your preferences.');
    } catch (error) {
      console.error('Error fetching recommendations:', error);
      Alert.alert('Error', 'Unable to fetch recommendations.');
    }
  };

  const handleTagSubmit = async (selectedTags: string[]) => {
    // Check if at least one tag is selected
    if (selectedTags.length === 0) {
      Alert.alert('No Tags Selected', 'Please select at least one tag before proceeding.');
      return; // Stop the function here
    }
  
    setLoading(true);
  
    try {
      if (!city) {
        Alert.alert('Error', 'Please enter a location.');
        setLoading(false);
        return;
      }
  
      // Geocode the address to get location coordinates
      const response = await axios.get(`${backendBaseURL}/geocode`, {
        params: { address: city },
      });
  
      const location = response.data; // Expected { latitude, longitude }
      if (!location) {
        Alert.alert('Error', 'Unable to determine location from city.');
        setLoading(false);
        return;
      }
    
      // Send the selected tags and location to the backend
      const placesResponse = await axios.post(`${backendBaseURL}/fetch-places`, {
        tags: selectedTags,
        location,
      });
  
      setPlaces(placesResponse.data); 
    } catch (error) {
      console.error('Error fetching places:', error);
      Alert.alert('Error fetching data');
    }
  
    setLoading(false);
  };
  

  const useCurrentLocation = async () => {
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== 'granted') {
        Alert.alert('Permission to access location was denied');
        return;
      }
  
      const location = await Location.getCurrentPositionAsync({});
      const { latitude, longitude } = location.coords;
  
      // Reverse geocode the current location to get the city and state
      const response = await axios.get(`${backendBaseURL}/geocode`, {
        params: { latitude, longitude },
      });
  
      const { city, state } = response.data;
      if (city && state) {
        setCity(`${city}, ${state}`); 
      } else {
        Alert.alert('Error', 'Unable to resolve location to a city and state.');
      }
    } catch (error) {
      console.error('Error fetching current location:', error);
      Alert.alert('Error', 'Unable to fetch current location.');
    }
  };  

  return (
    <View style={{ flex: 1, padding: 20 }}>
      <TextInput
        style={styles.input}
        placeholder="Enter User ID"
        value={userId}
        onChangeText={(text) => setUserId(text)}
      />
      <View style={styles.locationContainer}>
        <TextInput
          style={styles.cityInput}
          placeholder="Enter City"
          value={city}
          onChangeText={(text) => {
            setCity(text);
            fetchSuggestions(text);
          }}
        />
        <TouchableOpacity onPress={useCurrentLocation}>
          <Image
            source={{ uri: 'https://img.icons8.com/ios-filled/50/000000/marker.png' }}
            style={styles.locationIcon}
          />
        </TouchableOpacity>
      </View>
      {suggestions.length > 0 && (
        <FlatList
          data={suggestions}
          keyExtractor={(item) => item.place_id || item.description}
          renderItem={({ item }) => (
            <Text
              style={styles.suggestionItem}
              onPress={() => {
                setCity(item.description); // Pass full description
                setSuggestions([]); // Clear suggestions after selection
              }}
            >
              {item.description}
            </Text>
          )}
        />
      )}
      <TouchableOpacity style={styles.button} onPress={fetchRecommendations}>
        <Text style={styles.buttonText}>Get Recommendations</Text>
      </TouchableOpacity>
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

const styles = StyleSheet.create({
  input: {
    borderColor: '#ccc',
    borderWidth: 1,
    padding: 10,
    borderRadius: 5,
    marginBottom: 10,
  },
  locationContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 10,
  },
  cityInput: {
    flex: 1,
    borderColor: '#ccc',
    borderWidth: 1,
    padding: 10,
    borderRadius: 5,
  },
  locationIcon: {
    width: 30,
    height: 30,
    marginLeft: 10,
  },
  suggestionItem: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#ccc',
  },
  button: {
    backgroundColor: '#007bff',
    padding: 10,
    borderRadius: 5,
    alignItems: 'center',
    marginVertical: 10,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
  },
});

export default Index;
