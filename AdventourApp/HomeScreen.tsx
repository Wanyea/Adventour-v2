import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Animated,
  View,
  Text,
  TextInput,
  Alert,
  TouchableOpacity,
  Image,
  Linking,
  Keyboard,
  ScrollView,
} from 'react-native';
import { styles } from './src/styles/HomeScreenStyles';
import RecommendationDeck from './src/components/RecommendationDeck';
import PlaceDetailsModal from './src/components/PlaceDetailsModal';
import AdventourJourneyPanel from './src/components/AdventourJourneyPanel';
import AdventourLaunchHero from './src/components/AdventourLaunchHero';
import LocalEventsSection from './src/components/LocalEventsSection';
import { LaunchSuggestion } from './src/LaunchLocationService';
import LocationAutocompleteInput from './src/components/LocationAutocompleteInput';
import Config from './src/Config';
import { flushPilot, pilotConfig } from './src/pilot/PilotService';
import { recordPlaceEvent } from './src/services/PlaceEventService';
import Geolocation from '@react-native-community/geolocation';
import axios from 'axios';
import { AppState, PermissionsAndroid, Platform } from 'react-native';
import { Place } from './src/types/Place';
import { AdventourSession, AdventourStop } from './src/types/Adventour';
import { TAG_GROUPS, tagGroupDisplayLabel } from './src/placeTagGroups';
import AdventourService from './src/services/AdventourService';
import { User } from './src/services/AuthService';

import { Coordinates, LocationMode, RequestStep, RadiusOption, RADIUS_OPTIONS, describeAxiosError, placeFromRecommendation } from './src/home/homeUtils';

type HomeScreenProps = {
  user?: User | null;
};

const greetingForNow = () => {
  const hour = new Date().getHours();
  if (hour < 12) {
    return 'Good morning';
  }
  if (hour < 17) {
    return 'Good afternoon';
  }
  return 'Good evening';
};

const HomeScreen: React.FC<HomeScreenProps> = ({ user }) => {
  useEffect(() => {
    if (!Config.PILOT_BUILD || !user?.id) { return; }
    flushPilot().catch(() => {});
    const subscription = AppState.addEventListener('change', state => {
      if (state === 'active') { flushPilot().catch(() => {}); }
    });
    return () => subscription.remove();
  }, [user?.id]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [city, setCity] = useState<string>(''); 
  const [currentCoords, setCurrentCoords] = useState<Coordinates | null>(null);
  const [locationMode, setLocationMode] = useState<LocationMode>('none');
  const [launchError, setLaunchError] = useState('');
  const launchVersion = useRef(0);
  const [emptyMessage, setEmptyMessage] = useState<string>('');
  const [hasLoadedRecommendations, setHasLoadedRecommendations] = useState(false);
  const [autoRefillAvailable, setAutoRefillAvailable] = useState(false);
  const [radiusOption, setRadiusOption] = useState<RadiusOption>(RADIUS_OPTIONS[1]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [distanceOpen, setDistanceOpen] = useState(false);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [selectedTagGroup, setSelectedTagGroup] = useState<string>('all');
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [activeAdventour, setActiveAdventour] = useState<AdventourSession | null>(null);
  const [journeyLoading, setJourneyLoading] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const filterPanelAnim = useRef(new Animated.Value(0)).current;
  const recentlyDecidedPlaceIds = useRef(new Set<string>());
  const autoRefillInFlight = useRef(false);
  const pendingBasketScroll = useRef(false);
  const [basketOffsetY, setBasketOffsetY] = useState(0);
  const displayName = user?.display_name || user?.username || 'Adventourer';
  const hasLaunchPoint = Boolean(currentCoords);

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

  const [tagGroupCounts, setTagGroupCounts] = useState<Record<string, number>>({});

  const selectedTagLabel = selectedTagGroup === 'all'
    ? 'All picks'
    : tagGroupDisplayLabel(selectedTagGroup) || 'All picks';

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

  useEffect(() => {
    if (!pendingBasketScroll.current || loading || !hasLoadedRecommendations || places.length === 0) {
      return;
    }

    pendingBasketScroll.current = false;
    const timeout = setTimeout(() => {
      scrollRef.current?.scrollTo({
        y: Math.max(0, basketOffsetY - 12),
        animated: true,
      });
    }, 180);

    return () => clearTimeout(timeout);
  }, [basketOffsetY, hasLoadedRecommendations, loading, places.length]);

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
    const url = `https://www.google.com/maps/dir/?api=1&destination=${encodedDestination}`;

    try {
      await Linking.openURL(url);
      if (activeAdventour) {
        const result = await AdventourService.navigate(activeAdventour.id, stop.id);
        setActiveAdventour(result.adventour);
      }
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

  const handleRateStop = async (stop: AdventourStop, rating: number, notes: string) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.completeStop(activeAdventour.id, stop.id, rating, notes);
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

  const onImpression = useCallback(async (place: Place) => {
    await recordPlaceEvent(place, 'impression');
  }, []);

  const handleClosedReport = (place: Place) => {
    Alert.alert('Report closed?', 'This will remove the place from your recommendations.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Report closed', onPress: async () => {
        try {
          await recordPlaceEvent(place, 'closed_report');
          setSelectedPlace(null);
          setPlaces((previous) => previous.filter((item) => item.place_id !== place.place_id));
        } catch { Alert.alert('Report not saved', 'Please try again.'); }
      } },
    ]);
  };

  const handleFeedback = async (place: Place, feedback: 'accept' | 'reject') => {
    if (feedback === 'accept' && activeAdventour?.active_stop) {
      Alert.alert('Finish your current stop first', 'Mark arrival and rate the current place before choosing another stop.');
      return;
    }
    try {
      if (feedback === 'accept' && activeAdventour) {
        const result = await AdventourService.addStop(activeAdventour.id, place);
        setActiveAdventour(result.adventour);
      } else {
        await recordPlaceEvent(place, feedback);
      }
    } catch (error) {
      console.error('Could not save swipe:', describeAxiosError(error));
      Alert.alert('Swipe not saved', 'Your card is still here. Please try again.');
      return;
    }
    recentlyDecidedPlaceIds.current.add(place.place_id);
    if (place.provider_place_id) { recentlyDecidedPlaceIds.current.add(place.provider_place_id); }
    setPlaces((previous) => previous.filter((item) => item.place_id !== place.place_id));
    if (feedback === 'accept') {
      let googlePlaceId: string | undefined;
      try {
        const checked = await axios.get(`${Config.BACKEND_BASE_URL}/api/places/details`, { params: { place_id: place.place_id } });
        if (checked.data.verification === 'suppressed') {
          if (activeAdventour) { setActiveAdventour(await AdventourService.getActive()); }
          Alert.alert('Place unavailable', 'Choose another place for this stop.');
          return;
        }
        googlePlaceId = checked.data.google_place_id;
      } catch { /* Owned coordinates still work when live verification is unavailable. */ }
      const destination = place.approximate_location || place.latitude === undefined || place.longitude === undefined
        ? place.name : `${place.latitude},${place.longitude}`;
      try {
        const providerId = googlePlaceId ? `&destination_place_id=${encodeURIComponent(googlePlaceId)}` : '';
        await Linking.openURL(`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(destination)}${providerId}`);
        await recordPlaceEvent(place, 'navigate', activeAdventour ? 'adventour' : 'solo');
      } catch {
        Alert.alert('Place saved', 'Directions could not be opened or recorded. Your accepted place is in your history.');
      }
    }
  };

  const clearLaunchResults = () => {
    const version = ++launchVersion.current;
    setCurrentCoords(null);
    setLaunchError('');
    setPlaces([]);
    setSelectedPlace(null);
    setHasLoadedRecommendations(false);
    setTagGroupCounts({});
    setAutoRefillAvailable(false);
    setLoading(false);
    setLoadingMore(false);
    autoRefillInFlight.current = false;
    pendingBasketScroll.current = false;
    recentlyDecidedPlaceIds.current.clear();
    return version;
  };

  const handleCityChange = (text: string) => {
    clearLaunchResults();
    setCity(text);
    setLocationMode(text.trim() ? 'manual' : 'none');
  };

  const handleSuggestionSelect = (suggestion: LaunchSuggestion) => {
    clearLaunchResults();
    Keyboard.dismiss();
    setCity(suggestion.description);
    setLocationMode('manual');
    setCurrentCoords(null);

    const { latitude, longitude } = suggestion;
    if (Number.isFinite(latitude) && Math.abs(latitude) <= 90 && Number.isFinite(longitude) && Math.abs(longitude) <= 180) {
      setCurrentCoords({ latitude, longitude });
    } else {
      setLaunchError('Could not locate that selection. Try another result.');
    }
  };

  const loadRecommendations = useCallback(async ({ append = false, quiet = false, tagGroup = selectedTagGroup } = {}) => {
    const version = launchVersion.current;
    if (append) {
      if (autoRefillInFlight.current) {
        return;
      }
      autoRefillInFlight.current = true;
      setLoadingMore(true);
    } else {
      setLoading(true);
      setPlaces([]);
      setHasLoadedRecommendations(false);
      setAutoRefillAvailable(false);
      recentlyDecidedPlaceIds.current.clear();
    }
    setEmptyMessage(append ? 'Scouting more recommendations...' : 'Loading recommendations...');

    let step: RequestStep = 'recommendations';

    try {
      let recommendationResponse;
      const requestRecommendations = async (location: Coordinates) => axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations`, {
        mode: 'spontaneous',
        location_origin: locationMode,
        location,
        radius_meters: radiusOption.meters,
        constraints: {
          limit: 20,
          avoid_chains: true,
          tag_group: tagGroup,
          exclude_entity_ids: append ? Array.from(recentlyDecidedPlaceIds.current).slice(-500) : [],
        },
      }, await pilotConfig());

      if (locationMode === 'gps' && currentCoords) {
        step = 'recommendations';
        console.log('Finding places using GPS coordinates:', currentCoords);
        recommendationResponse = await requestRecommendations(currentCoords);
      } else if (locationMode === 'manual' && currentCoords) {
        step = 'recommendations';
        console.log('Finding places using saved manual destination:', currentCoords);
        recommendationResponse = await requestRecommendations(currentCoords);
      } else if (city.trim()) {
        step = 'geocode';
        console.log('Resolving manual destination:', city.trim());
        const geocodeResponse = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
          params: { address: city.trim() },
        });
        if (version !== launchVersion.current) return;
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
        recommendationResponse = await requestRecommendations(resolvedLocation);
      } else {
        if (!quiet) {
          Alert.alert('Error', 'Please enter a location or enable GPS.');
        }
        return;
      }

      if (version !== launchVersion.current) return;
      setTagGroupCounts(recommendationResponse.data.tag_group_counts || {});
      const recommendations = recommendationResponse.data.recommendations || [];
      const results = recommendations
        .map(placeFromRecommendation)
        .filter((place: Place) => (
          !recentlyDecidedPlaceIds.current.has(place.place_id)
          && (!place.provider_place_id || !recentlyDecidedPlaceIds.current.has(String(place.provider_place_id)))
        ));

      const existingIds = new Set(
        places.flatMap((place) => [
          place.place_id,
          place.provider_place_id ? String(place.provider_place_id) : '',
        ]).filter(Boolean),
      );
      const freshResults = append
        ? results.filter((place: Place) => (
          !existingIds.has(place.place_id)
          && (!place.provider_place_id || !existingIds.has(String(place.provider_place_id)))
        ))
        : results;

      setPlaces(append ? [...places, ...freshResults] : freshResults);
      setHasLoadedRecommendations(true);
      setAutoRefillAvailable(freshResults.length > 0);
      if (!append) {
        setSelectedTagGroup(tagGroup);
        pendingBasketScroll.current = freshResults.length > 0;
      }
      if (freshResults.length > 0 || append) {
        setEmptyMessage(freshResults.length > 0 ? '' : 'No new places found yet. Try refreshing or widening the search distance.');
      } else {
        const providerErrors = recommendationResponse.data.provider_errors || [];
        const hasProviderErrors = providerErrors.length > 0;
        const message = hasProviderErrors
          ? 'No places found because the place provider lookup failed.'
          : 'No places found for this search. Try a wider distance or a different location.';
        setEmptyMessage(message);
        setHasLoadedRecommendations(true);
      }
    } catch (error: unknown) {
      if (version !== launchVersion.current) return;
      const details = describeAxiosError(error);
      console.error(`Error during ${step}:`, details);
      const message = step === 'geocode'
        ? 'Choose a location from the suggestions, or use GPS.'
        : 'Unable to load recommendations for that destination.';
      setEmptyMessage(message);
      if (!append) {
        setHasLoadedRecommendations(false);
      }
      setAutoRefillAvailable(false);
      if (!quiet) {
        Alert.alert('Error', message);
      }
    } finally {
      if (version !== launchVersion.current) {
        // A newer launch owns the loading state.
      } else if (append) {
        setLoadingMore(false);
        autoRefillInFlight.current = false;
      } else {
        setLoading(false);
      }
    }
  }, [city, currentCoords, locationMode, places, radiusOption.meters, selectedTagGroup]);

  const handleFindPlaces = () => {
    loadRecommendations({ append: false });
  };

  const handleRecommendationDeckExhausted = useCallback(() => {
    loadRecommendations({ append: true, quiet: true });
  }, [loadRecommendations]);

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
    const version = clearLaunchResults();
    const granted = await requestLocationPermission();
    if (version !== launchVersion.current) return;
    if (!granted) {
      Alert.alert("Permission Denied", "Location access is required.");
      return;
    }

    Geolocation.getCurrentPosition(
      async (position) => {
        if (version !== launchVersion.current) return;
        const { latitude, longitude } = position.coords;
        setCurrentCoords({ latitude, longitude });
        setLocationMode('gps');

        try {
          const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
            params: { latitude, longitude },
          });
          if (version !== launchVersion.current) return;

          const { city, state } = response.data;
          if (city && state) {
            setCity(`${city}, ${state}`);
          } else {
            Alert.alert('Error', 'Unable to resolve location to a city and state.');
          }
        } catch (error) {
          if (version !== launchVersion.current) return;
          console.error('Error fetching geocoded location:', error);
          setCity(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        }
      },
      (error) => {
        if (version !== launchVersion.current) return;
        console.error('Geolocation error:', error);
        Alert.alert("Location Error", error.message);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 }
    );
  };

  return (
    <View style={styles.screen}>
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.greetingBlock}>
          <Text style={styles.greetingText}>{greetingForNow()}, {displayName}</Text>
        </View>
        <View style={[styles.launchControls, !hasLaunchPoint && styles.launchControlsRequired]}>
          <View style={styles.launchControlHeader}>
            <Text style={[styles.controlLabel, !hasLaunchPoint && styles.controlLabelRequired]}>
              {hasLaunchPoint ? 'Launch point' : 'Pick a launch point'}
            </Text>
          </View>
          <View style={styles.locationContainer}>
            <LocationAutocompleteInput
              placeholder="City, neighborhood, or place"
              value={city}
              onChangeText={handleCityChange}
              placeholderTextColor="#6b8aa3"
              inputStyle={[styles.cityInput, !hasLaunchPoint && styles.cityInputRequired]}
              onSelectSuggestion={handleSuggestionSelect}
              onSearchError={setLaunchError}
              trailingContent={(
                <>
                  <TouchableOpacity style={styles.locationButton} onPress={useCurrentLocation}>
                    <Image
                      source={{ uri: 'https://img.icons8.com/ios-filled/50/ffffff/marker.png' }}
                      style={styles.locationIcon}
                    />
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.locationButton, styles.filterIconButton, filtersOpen && styles.filterIconButtonActive]}
                    onPress={() => setFiltersOpen((open) => !open)}
                    activeOpacity={0.82}
                    accessibilityLabel="Open filters"
                  >
                    <View style={styles.filterGlyph}>
                      <View style={[styles.filterGlyphLine, styles.filterGlyphLineTop]} />
                      <View style={[styles.filterGlyphLine, styles.filterGlyphLineMiddle]} />
                      <View style={[styles.filterGlyphLine, styles.filterGlyphLineBottom]} />
                    </View>
                  </TouchableOpacity>
                </>
              )}
            />
          </View>
          {launchError ? <Text style={styles.suggestionText}>{launchError}</Text> : null}
          <Text style={styles.suggestionText} onPress={() => Linking.openURL('https://www.openstreetmap.org/copyright')}>
            Location search: © OpenStreetMap contributors
          </Text>
        </View>
        {filtersOpen ? (
          <View style={styles.filterSection}>
            <Animated.View style={[styles.filterPanel, filterPanelStyle]}>
              <View style={styles.filterPanelHeader}>
                <View>
                  <Text style={styles.filterTitle}>Filters</Text>
                  <Text style={styles.filterSummary}>
                    {radiusOption.label}{hasLoadedRecommendations ? ` - ${selectedTagLabel}` : ''}
                  </Text>
                </View>
                <TouchableOpacity onPress={() => setFiltersOpen(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Text style={styles.dropdownValue}>Close</Text>
                </TouchableOpacity>
              </View>
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
                      loadRecommendations({ tagGroup: 'all' });
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
                          loadRecommendations({ tagGroup: group.id });
                        }}
                      >
                        <Text
                          style={[
                            styles.dropdownItemText,
                            disabled && styles.dropdownItemTextDisabled,
                            selected && styles.dropdownItemTextSelected,
                          ]}
                        >
                          {group.emoji} {group.label} ({count})
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
          </View>
        ) : null}
        <AdventourLaunchHero
          locationLabel={city || (currentCoords ? 'GPS location' : '')}
          distanceLabel={`${radiusOption.label} range`}
          loading={loading}
          hasResults={hasLoadedRecommendations}
          hasLaunchPoint={hasLaunchPoint}
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
        <View
          onLayout={(event) => setBasketOffsetY(event.nativeEvent.layout.y)}
        >
          {loading ? (
            <Text style={styles.emptyText}>Loading...</Text>
          ) : hasLoadedRecommendations ? (
            <RecommendationDeck
              pilotActive={!selectedPlace}
              places={filteredPlaces}
              activeFilterLabel={selectedTagLabel}
              totalPlaces={places.length}
              loadingMore={loadingMore}
              canLoadMore={autoRefillAvailable}
              onFeedback={handleFeedback}
              onImpression={onImpression}
              onOpenPlace={setSelectedPlace}
              onExhausted={handleRecommendationDeckExhausted}
            />
          ) : (
            <Text style={styles.emptyText}>{emptyMessage}</Text>
          )}
        </View>
        {currentCoords ? <LocalEventsSection key={`${currentCoords.latitude}/${currentCoords.longitude}`} coordinates={currentCoords} /> : null}
      </ScrollView>
      <PlaceDetailsModal
        onClosedReport={handleClosedReport}
        place={selectedPlace}
        visible={Boolean(selectedPlace)}
        onClose={() => setSelectedPlace(null)}
      />
    </View>
  );
};


export default HomeScreen;
