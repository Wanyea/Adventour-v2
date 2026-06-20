import React, { useRef, useState } from 'react';
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
import PlaceList from './src/PlaceList';
import GoogleAutocompleteService from './src/GoogleAutocompleteService';
import Config from './src/Config';
import Geolocation from '@react-native-community/geolocation';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';
import { useEffect } from 'react';
import { PermissionsAndroid, Platform } from 'react-native';
import { Place } from './src/types/Place';

type Coordinates = { latitude: number; longitude: number };
type LocationMode = 'none' | 'gps' | 'manual';
type RequestStep = 'geocode' | 'recommendations';

const describeAxiosError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    return {
      message: error.message,
      code: error.code,
      status: error.response?.status,
      data: error.response?.data,
      url: error.config?.url,
      method: error.config?.method,
    };
  }
  return error;
};

const HomeScreen: React.FC = () => {
  const backendBaseURL = Config.BACKEND_BASE_URL;
  const [places, setPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [userFeedback, setUserFeedback] = useState<{ place_id: string; feedback: string; tags: string[] }[]>([]);
  const [userId, setUserId] = useState<string>('');
  const [city, setCity] = useState<string>(''); 
  const [currentCoords, setCurrentCoords] = useState<Coordinates | null>(null);
  const [locationMode, setLocationMode] = useState<LocationMode>('none');
  const [suggestions, setSuggestions] = useState<any[]>([]); 
  const [emptyMessage, setEmptyMessage] = useState<string>('No places found...');
  const autocompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const getOrCreateUserId = async () => {
      try {
        let id = await AsyncStorage.getItem('user_id');
        if (!id) {
          id = uuidv4();
          await AsyncStorage.setItem('user_id', id);
        }
        setUserId(id);
      } catch (e) {
        console.error("Failed to initialize user ID", e);
      }
    };
    getOrCreateUserId();
  }, []);

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

  const fetchSuggestions = async (input: string, biasLocation: Coordinates | null = currentCoords) => {
    if (autocompleteTimer.current) {
      clearTimeout(autocompleteTimer.current);
    }

    if (input.length <= 2) {
      setSuggestions([]);
      return;
    }

    autocompleteTimer.current = setTimeout(async () => {
      const autocompleteSuggestions = await GoogleAutocompleteService.fetchAutocompleteSuggestions(input, biasLocation);
      setSuggestions(autocompleteSuggestions);
    }, 350);
  };

  const handleCityChange = (text: string) => {
    setCity(text);
    setLocationMode(text.trim() ? 'manual' : 'none');
    setCurrentCoords(null);
    fetchSuggestions(text, null);
  };

  const handleSuggestionSelect = (description: string) => {
    setCity(description);
    setLocationMode('manual');
    setCurrentCoords(null);
    setSuggestions([]);
  };

  const handleFindPlaces = async () => {
    setLoading(true);
    setPlaces([]);
    setEmptyMessage('Loading recommendations...');

    let step: RequestStep = 'recommendations';

    try {
      let recommendationResponse;
      if (locationMode === 'gps' && currentCoords) {
        step = 'recommendations';
        console.log('Finding places using GPS coordinates:', currentCoords);
        recommendationResponse = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations`, {
          mode: 'spontaneous',
          location: currentCoords,
          constraints: {
            limit: 20,
            avoid_chains: true,
          },
        });
      } else if (city.trim()) {
        step = 'geocode';
        console.log('Resolving manual destination:', city.trim());
        const geocodeResponse = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
          params: { address: city.trim() },
        });
        const resolvedLocation = {
          latitude: Number(geocodeResponse.data.latitude),
          longitude: Number(geocodeResponse.data.longitude),
        };
        if (!Number.isFinite(resolvedLocation.latitude) || !Number.isFinite(resolvedLocation.longitude)) {
          throw new Error(`Unable to resolve coordinates for ${city}`);
        }
        setCurrentCoords(resolvedLocation);
        setLocationMode('manual');
        step = 'recommendations';
        console.log('Finding places using resolved destination:', resolvedLocation);
        recommendationResponse = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations`, {
          mode: 'spontaneous',
          location: resolvedLocation,
          constraints: {
            limit: 20,
            avoid_chains: true,
          },
        });
      } else {
        Alert.alert('Error', 'Please enter a location or enable GPS.');
        return;
      }

      const recommendations = recommendationResponse.data.recommendations || [];
      const results = recommendations.map((item: any) => ({
        place_id: String(item.place_id || item.provider_place_id),
        name: item.name || item.display?.name || 'Unknown place',
        vicinity: item.display?.vicinity || `${item.distance_meters ?? 'Unknown'} meters away`,
        types: item.display?.types || [],
        rating: item.display?.rating,
        user_ratings_total: item.display?.user_ratings_total,
        price_level: item.display?.price_level,
        relevance: item.score,
        likelihood: item.score,
      }));

      setPlaces(results);
      if (results.length > 0) {
        Alert.alert('Places loaded!', `We found ${results.length} match${results.length === 1 ? '' : 'es'} for you.`);
      } else {
        const providerErrors = recommendationResponse.data.provider_errors || [];
        const hasProviderErrors = providerErrors.length > 0;
        const message = hasProviderErrors
          ? 'No places found. Local seed data is empty and the provider lookup failed.'
          : 'No places found yet. Try a different location or seed local places for development.';
        setEmptyMessage(message);
        Alert.alert('No places found', message);
      }
    } catch (error: unknown) {
      const details = describeAxiosError(error);
      console.error(`Error during ${step}:`, details);
      const message = step === 'geocode'
        ? 'Unable to resolve that destination. Try a more specific city, state, or address.'
        : 'Unable to load recommendations for that destination.';
      setEmptyMessage(message);
      Alert.alert('Error', message);
    } finally {
      setLoading(false);
    }
  };

  const requestLocationPermission = async () => {
    if (Platform.OS === 'android') {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
        {
          title: "Location Permission",
          message: "Adventour needs access to your location.",
          buttonPositive: "OK"
        }
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    }
    return true;
  };

  const useCurrentLocation = async () => {
    const granted = await requestLocationPermission();
    if (!granted) {
      Alert.alert("Permission Denied", "Location access is required.");
      return;
    }

    Geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setCurrentCoords({ latitude, longitude });
        setLocationMode('gps');

        try {
          const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
            params: { latitude, longitude },
          });

          const { city, state } = response.data;
          if (city && state) {
            setCity(`${city}, ${state}`);
          } else {
            Alert.alert('Error', 'Unable to resolve location to a city and state.');
          }
        } catch (error) {
          console.error('Error fetching geocoded location:', error);
          setCity(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
          Alert.alert(
            'Location selected',
            'Using your GPS coordinates. City lookup is unavailable in local dev without geocoding.'
          );
        }
      },
      (error) => {
        console.error('Geolocation error:', error);
        Alert.alert("Location Error", error.message);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 }
    );
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
          onChangeText={handleCityChange}
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
              onPress={() => handleSuggestionSelect(item.description)}
            >
              {item.description}
            </Text>
          )}
        />
      )}
      <TouchableOpacity style={styles.button} onPress={handleFindPlaces}>
        <Text style={styles.buttonText}>Find Places</Text>
      </TouchableOpacity>
      {loading ? (
        <Text>Loading...</Text>
      ) : places.length > 0 ? (
        <PlaceList places={places} onFeedback={handleFeedback} />
      ) : (
        <Text>{emptyMessage}</Text>
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

export default HomeScreen;
