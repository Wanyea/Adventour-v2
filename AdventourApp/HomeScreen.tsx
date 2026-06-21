import React, { useRef, useState } from 'react';
import {
  Animated,
  View,
  Text,
  TextInput,
  Alert,
  TouchableOpacity,
  StyleSheet,
  Image,
  Linking,
  ScrollView,
} from 'react-native';
import RecommendationDeck from './src/components/RecommendationDeck';
import PlaceDetailsModal from './src/components/PlaceDetailsModal';
import AdventourJourneyPanel from './src/components/AdventourJourneyPanel';
import AdventourLaunchHero from './src/components/AdventourLaunchHero';
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
import { AdventourSession, AdventourStop } from './src/types/Adventour';
import { TAG_GROUPS, tagGroupIdsForPlace } from './src/placeTagGroups';
import AdventourService from './src/services/AdventourService';

type Coordinates = { latitude: number; longitude: number };
type LocationMode = 'none' | 'gps' | 'manual';
type RequestStep = 'geocode' | 'recommendations';
type RadiusOption = {
  id: 'walkable' | 'nearby' | 'explore' | 'wide';
  label: string;
  helper: string;
  meters: number;
};

const RADIUS_OPTIONS: RadiusOption[] = [
  { id: 'walkable', label: 'Walkable', helper: '10 min', meters: 800 },
  { id: 'nearby', label: 'Nearby', helper: '2 mi', meters: 3200 },
  { id: 'explore', label: 'Explore', helper: '5 mi', meters: 8000 },
  { id: 'wide', label: 'Wide', helper: '10 mi', meters: 16000 },
];

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
  const [hasLoadedRecommendations, setHasLoadedRecommendations] = useState(false);
  const [radiusOption, setRadiusOption] = useState<RadiusOption>(RADIUS_OPTIONS[1]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [distanceOpen, setDistanceOpen] = useState(false);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [selectedTagGroup, setSelectedTagGroup] = useState<string>('all');
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [activeAdventour, setActiveAdventour] = useState<AdventourSession | null>(null);
  const [journeyLoading, setJourneyLoading] = useState(false);
  const autocompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const filterPanelAnim = useRef(new Animated.Value(0)).current;

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

  useEffect(() => {
    const loadActiveAdventour = async () => {
      try {
        const adventour = await AdventourService.getActive();
        setActiveAdventour(adventour);
      } catch (error) {
        console.error('Error loading active Adventour:', describeAxiosError(error));
      }
    };

    loadActiveAdventour();
  }, []);

  const filteredPlaces = selectedTagGroup === 'all'
    ? places
    : places.filter((place) => place.tag_groups?.includes(selectedTagGroup));

  const tagGroupCounts = TAG_GROUPS.reduce<Record<string, number>>((counts, group) => {
    counts[group.id] = places.filter((place) => place.tag_groups?.includes(group.id)).length;
    return counts;
  }, {});

  const selectedTagLabel = selectedTagGroup === 'all'
    ? 'All picks'
    : TAG_GROUPS.find((group) => group.id === selectedTagGroup)?.label || 'All picks';

  useEffect(() => {
    if (selectedTagGroup !== 'all' && places.length > 0 && filteredPlaces.length === 0) {
      setSelectedTagGroup('all');
    }
  }, [filteredPlaces.length, places.length, selectedTagGroup]);

  useEffect(() => {
    Animated.timing(filterPanelAnim, {
      toValue: filtersOpen ? 1 : 0,
      duration: 170,
      useNativeDriver: true,
    }).start();
  }, [filterPanelAnim, filtersOpen]);

  const filterPanelStyle = {
    opacity: filterPanelAnim,
    transform: [
      {
        translateY: filterPanelAnim.interpolate({
          inputRange: [0, 1],
          outputRange: [-6, 0],
        }),
      },
    ],
  };

  const showTagDescription = (groupId: string) => {
    if (groupId === 'all') {
      Alert.alert('All picks', 'Show every recommendation from the current search, ordered by Adventour score.');
      return;
    }
    const group = TAG_GROUPS.find((item) => item.id === groupId);
    if (group) {
      Alert.alert(group.label, group.description);
    }
  };

  const openDirectionsForStop = async (stop: AdventourStop) => {
    const destination = stop.display?.latitude && stop.display?.longitude
      ? `${stop.display.latitude},${stop.display.longitude}`
      : stop.display?.name || '';
    const encodedDestination = encodeURIComponent(destination);
    const providerPlaceId = stop.provider_place_id
      ? `&destination_place_id=${encodeURIComponent(stop.provider_place_id)}`
      : '';
    const url = `https://www.google.com/maps/dir/?api=1&destination=${encodedDestination}${providerPlaceId}`;

    try {
      await Linking.openURL(url);
    } catch (error) {
      console.error('Error opening directions:', error);
      Alert.alert('Directions unavailable', 'Adventour could not open your maps app.');
    }
  };

  const handleStartAdventour = async () => {
    setJourneyLoading(true);
    try {
      const adventour = await AdventourService.start(city ? `${city} Adventour` : undefined);
      setActiveAdventour(adventour);
    } catch (error) {
      console.error('Error starting Adventour:', describeAxiosError(error));
      Alert.alert('Could not start Adventour', 'Try again in a moment.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleArriveAtStop = async (stop: AdventourStop) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.arrive(activeAdventour.id, stop.id);
      setActiveAdventour(result.adventour);
    } catch (error) {
      console.error('Error marking arrival:', describeAxiosError(error));
      Alert.alert('Arrival not saved', 'Adventour could not mark this stop as arrived.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleRateStop = async (stop: AdventourStop, rating: number) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.completeStop(activeAdventour.id, stop.id, rating);
      setActiveAdventour(result.adventour);
    } catch (error) {
      console.error('Error completing stop:', describeAxiosError(error));
      Alert.alert('Rating not saved', 'Adventour could not finish this stop.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleEndAdventour = async () => {
    if (!activeAdventour) {
      return;
    }

    Alert.alert(
      'End Adventour?',
      'This will save your journey recap and clear the active trip.',
      [
        { text: 'Keep going', style: 'cancel' },
        {
          text: 'End',
          style: 'destructive',
          onPress: async () => {
            setJourneyLoading(true);
            try {
              const completed = await AdventourService.complete(activeAdventour.id);
              setActiveAdventour(null);
              setEmptyMessage(
                `Adventour complete. Saved ${completed.summary?.stop_count || 0} stop${(completed.summary?.stop_count || 0) === 1 ? '' : 's'} to your Passport.`
              );
            } catch (error) {
              console.error('Error ending Adventour:', describeAxiosError(error));
              Alert.alert('Could not end Adventour', 'Try again in a moment.');
            } finally {
              setJourneyLoading(false);
            }
          },
        },
      ],
    );
  };

  const handleFeedback = async (place: Place, feedback: 'accept' | 'reject') => {
    if (feedback === 'accept' && activeAdventour?.active_stop) {
      Alert.alert(
        'Finish your current stop first',
        'Mark yourself as arrived and rate the current place before adding another Adventour stop.'
      );
      return;
    }

    setUserFeedback((prev) => [
      ...prev,
      { place_id: place.place_id, feedback, tags: place.types },
    ]);
    setPlaces((prev) => prev.filter((item) => item.place_id !== place.place_id));

    try {
      const response = await axios.post(`${backendBaseURL}/api/events`, {
        place_id: place.place_id,
        provider: place.provider,
        provider_place_id: place.provider_place_id,
        event_type: feedback,
        context: selectedTagGroup === 'all' ? 'solo' : selectedTagGroup,
        metadata: {
          source: 'recommendation_deck',
          category: place.category,
          active_tag_group: selectedTagGroup,
          score: place.relevance,
          tags: place.types,
          display: {
            name: place.name,
            vicinity: place.vicinity,
            types: place.types,
            category: place.category,
            tag_groups: place.tag_groups || [],
            photo_url: place.photo_url
              ? place.photo_url.replace(Config.BACKEND_BASE_URL, '')
              : undefined,
            photo_attributions: place.photo_attributions || [],
            rating: place.rating,
            user_ratings_total: place.user_ratings_total,
            price_level: place.price_level,
          },
        },
      });
      console.log(response.data);

      if (feedback === 'accept' && activeAdventour) {
        const result = await AdventourService.addStop(activeAdventour.id, place);
        setActiveAdventour(result.adventour);
      }
    } catch (error) {
      console.error('Error saving feedback event:', describeAxiosError(error));
      Alert.alert('Feedback not saved', 'The card was removed locally, but Adventour could not save that swipe.');
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
      const autocompleteSuggestions = await GoogleAutocompleteService.fetchAutocompleteSuggestions(
        input,
        biasLocation,
        radiusOption.meters,
      );
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
    setHasLoadedRecommendations(false);
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
          radius_meters: radiusOption.meters,
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
          radius_meters: radiusOption.meters,
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
      const results = recommendations.map((item: any) => {
        const name = item.name || item.display?.name || 'Unknown place';
        const types = item.display?.types || [];
        const place = {
          place_id: String(item.place_id || item.provider_place_id),
          provider: item.provider,
          provider_place_id: item.provider_place_id,
          name,
          vicinity: item.display?.vicinity || `${item.distance_meters ?? 'Unknown'} meters away`,
          types,
          category: item.category,
          explanation: item.explanation,
          photo_url: item.display?.photo_url
            ? `${Config.BACKEND_BASE_URL}${item.display.photo_url}`
            : undefined,
          photo_attributions: item.display?.photo_attributions || [],
          rating: item.display?.rating,
          user_ratings_total: item.display?.user_ratings_total,
          price_level: item.display?.price_level,
          relevance: item.score,
          likelihood: item.score,
          latitude: item.latitude,
          longitude: item.longitude,
          distance_meters: item.distance_meters,
          travel_times: item.travel_times,
        };
        return {
          ...place,
          tag_groups: tagGroupIdsForPlace(place),
        };
      });

      setPlaces(results);
      setHasLoadedRecommendations(results.length > 0);
      setSelectedTagGroup('all');
      if (results.length > 0) {
        setEmptyMessage('');
      } else {
        const providerErrors = recommendationResponse.data.provider_errors || [];
        const hasProviderErrors = providerErrors.length > 0;
        const message = hasProviderErrors
          ? 'No places found because the place provider lookup failed.'
          : 'No places found for this search. Try a wider distance or a different location.';
        setEmptyMessage(message);
        setHasLoadedRecommendations(false);
      }
    } catch (error: unknown) {
      const details = describeAxiosError(error);
      console.error(`Error during ${step}:`, details);
      const message = step === 'geocode'
        ? 'Unable to resolve that destination. Try a more specific city, state, or address.'
        : 'Unable to load recommendations for that destination.';
      setEmptyMessage(message);
      setHasLoadedRecommendations(false);
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
    <View style={styles.screen}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.launchControls}>
          <Text style={styles.controlLabel}>Launch point</Text>
          <View style={styles.locationContainer}>
            <TextInput
              style={styles.cityInput}
              placeholder="Enter a city or place"
              value={city}
              onChangeText={handleCityChange}
              placeholderTextColor="#6b8aa3"
            />
            <TouchableOpacity style={styles.locationButton} onPress={useCurrentLocation}>
              <Image
                source={{ uri: 'https://img.icons8.com/ios-filled/50/ffffff/marker.png' }}
                style={styles.locationIcon}
              />
            </TouchableOpacity>
          </View>
        </View>
        {suggestions.length > 0 && (
          <View style={styles.suggestionsList}>
            {suggestions.map((item) => (
              <TouchableOpacity
                key={item.place_id || item.description}
                style={styles.suggestionItem}
                onPress={() => handleSuggestionSelect(item.description)}
              >
                <Text style={styles.suggestionText}>{item.description}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
        <View style={styles.filterSection}>
          <TouchableOpacity
            style={styles.filterToggle}
            activeOpacity={0.82}
            onPress={() => setFiltersOpen((open) => !open)}
          >
            <View>
              <Text style={styles.filterTitle}>Filters</Text>
              <Text style={styles.filterSummary}>
                {radiusOption.label}{hasLoadedRecommendations ? ` - ${selectedTagLabel}` : ''}
              </Text>
            </View>
            <Text style={styles.dropdownValue}>{filtersOpen ? 'Hide' : 'Show'}</Text>
          </TouchableOpacity>

          {filtersOpen ? (
            <Animated.View style={[styles.filterPanel, filterPanelStyle]}>
              <TouchableOpacity
                style={styles.dropdownButton}
                activeOpacity={0.8}
                onPress={() => setDistanceOpen((open) => !open)}
              >
                <Text style={styles.dropdownLabel}>Search distance</Text>
                <Text style={styles.dropdownValue}>{radiusOption.label} ({radiusOption.helper})</Text>
              </TouchableOpacity>
              {distanceOpen ? (
                <View style={styles.dropdownMenu}>
                  {RADIUS_OPTIONS.map((option) => {
                    const selected = option.id === radiusOption.id;
                    return (
                      <TouchableOpacity
                        key={option.id}
                        style={[styles.dropdownItem, selected && styles.dropdownItemSelected]}
                        onPress={() => {
                          setRadiusOption(option);
                          setDistanceOpen(false);
                        }}
                      >
                        <Text style={[styles.dropdownItemText, selected && styles.dropdownItemTextSelected]}>
                          {option.label}
                        </Text>
                        <Text style={[styles.dropdownHelperText, selected && styles.dropdownItemTextSelected]}>
                          {option.helper}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ) : null}

              <TouchableOpacity
                style={[styles.dropdownButton, !hasLoadedRecommendations && styles.dropdownButtonDisabled]}
                activeOpacity={hasLoadedRecommendations ? 0.8 : 1}
                onPress={() => hasLoadedRecommendations && setTagDropdownOpen((open) => !open)}
              >
                <Text style={styles.dropdownLabel}>Tag group</Text>
                <Text style={styles.dropdownValue}>
                  {hasLoadedRecommendations ? selectedTagLabel : 'Available after search'}
                </Text>
              </TouchableOpacity>
              {hasLoadedRecommendations && tagDropdownOpen ? (
                <View style={styles.dropdownMenu}>
                  <TouchableOpacity
                    style={[styles.dropdownItem, selectedTagGroup === 'all' && styles.dropdownItemSelected]}
                    onPress={() => {
                      setSelectedTagGroup('all');
                      setTagDropdownOpen(false);
                    }}
                  >
                    <Text style={[styles.dropdownItemText, selectedTagGroup === 'all' && styles.dropdownItemTextSelected]}>
                      All picks
                    </Text>
                    <TouchableOpacity onPress={() => showTagDescription('all')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <Text style={[styles.tagInfo, selectedTagGroup === 'all' && styles.dropdownItemTextSelected]}>?</Text>
                    </TouchableOpacity>
                  </TouchableOpacity>
                  {TAG_GROUPS.map((group) => {
                    const selected = selectedTagGroup === group.id;
                    const count = tagGroupCounts[group.id] || 0;
                    const disabled = count === 0;
                    return (
                      <TouchableOpacity
                        key={group.id}
                        style={[
                          styles.dropdownItem,
                          disabled && styles.dropdownItemDisabled,
                          selected && styles.dropdownItemSelected,
                        ]}
                        activeOpacity={disabled ? 1 : 0.8}
                        onPress={() => {
                          if (disabled) {
                            return;
                          }
                          setSelectedTagGroup(group.id);
                          setTagDropdownOpen(false);
                        }}
                      >
                        <Text
                          style={[
                            styles.dropdownItemText,
                            disabled && styles.dropdownItemTextDisabled,
                            selected && styles.dropdownItemTextSelected,
                          ]}
                        >
                          {group.label} ({count})
                        </Text>
                        <TouchableOpacity onPress={() => showTagDescription(group.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                          <Text style={[styles.tagInfo, selected && styles.dropdownItemTextSelected]}>?</Text>
                        </TouchableOpacity>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ) : null}
            </Animated.View>
          ) : null}
        </View>
        <AdventourLaunchHero
          locationLabel={city || (currentCoords ? 'GPS location' : 'Pick your launch point')}
          distanceLabel={`${radiusOption.label} range`}
          loading={loading}
          hasResults={hasLoadedRecommendations}
          activeStopName={activeAdventour?.active_stop?.display?.name}
          onLaunch={handleFindPlaces}
        />
        <AdventourJourneyPanel
          adventour={activeAdventour}
          loading={journeyLoading}
          onStart={handleStartAdventour}
          onOpenDirections={openDirectionsForStop}
          onArrive={handleArriveAtStop}
          onRateStop={handleRateStop}
          onEnd={handleEndAdventour}
        />
        {loading ? (
          <Text style={styles.emptyText}>Loading...</Text>
        ) : hasLoadedRecommendations ? (
          <RecommendationDeck
            places={filteredPlaces}
            activeFilterLabel={selectedTagLabel}
            totalPlaces={places.length}
            onFeedback={handleFeedback}
            onOpenPlace={setSelectedPlace}
          />
        ) : (
          <Text style={styles.emptyText}>{emptyMessage}</Text>
        )}
      </ScrollView>
      <PlaceDetailsModal
        place={selectedPlace}
        visible={Boolean(selectedPlace)}
        onClose={() => setSelectedPlace(null)}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#bfeaf4',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 28,
  },
  launchControls: {
    backgroundColor: '#dff6f2',
    borderRadius: 8,
    padding: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#87cfe1',
  },
  controlLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 7,
    textTransform: 'uppercase',
  },
  input: {
    borderColor: '#eadfce',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    marginBottom: 8,
    backgroundColor: '#fff',
    color: '#1f2937',
  },
  locationContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  cityInput: {
    flex: 1,
    borderColor: '#87cfe1',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#fff',
    color: '#123c69',
    fontWeight: '700',
  },
  locationButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#123c69',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 9,
  },
  locationIcon: {
    width: 24,
    height: 24,
  },
  suggestionsList: {
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    overflow: 'hidden',
    marginBottom: 8,
  },
  suggestionItem: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eadfce',
  },
  suggestionText: {
    color: '#1f2937',
    fontSize: 13,
  },
  emptyText: {
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 8,
  },
  filterSection: {
    marginTop: 0,
    marginBottom: 8,
  },
  filterToggle: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#dff6f2',
    paddingHorizontal: 10,
    paddingVertical: 9,
    shadowColor: '#123c69',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 5,
    elevation: 2,
  },
  filterPanel: {
    marginTop: 8,
  },
  filterTitle: {
    fontSize: 13,
    fontWeight: '900',
    color: '#134e4a',
  },
  filterSummary: {
    marginTop: 2,
    color: '#31506b',
    fontSize: 12,
  },
  dropdownButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 9,
    marginBottom: 6,
  },
  dropdownLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '800',
  },
  dropdownValue: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  dropdownMenu: {
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    overflow: 'hidden',
    marginBottom: 8,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  dropdownItemSelected: {
    backgroundColor: '#123c69',
  },
  dropdownItemDisabled: {
    backgroundColor: '#f9fafb',
  },
  dropdownItemText: {
    fontSize: 12,
    fontWeight: '800',
    color: '#123c69',
  },
  dropdownHelperText: {
    fontSize: 12,
    color: '#31506b',
  },
  dropdownItemTextDisabled: {
    color: '#a3a3a3',
  },
  dropdownItemTextSelected: {
    color: '#fff',
  },
  dropdownButtonDisabled: {
    opacity: 0.6,
  },
  tagInfo: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '900',
  },
  button: {
    backgroundColor: '#0f766e',
    paddingVertical: 9,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 8,
    shadowColor: '#0f766e',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.18,
    shadowRadius: 6,
    elevation: 3,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '900',
  },
});

export default HomeScreen;
