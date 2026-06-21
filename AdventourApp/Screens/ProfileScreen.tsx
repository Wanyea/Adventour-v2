import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ImageBackground,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useFocusEffect } from '@react-navigation/native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import Config from '../src/Config';
import PlaceDetailsModal from '../src/components/PlaceDetailsModal';
import { Place } from '../src/types/Place';
import { AdventourSession } from '../src/types/Adventour';

const passportCard = require('../src/assets/profile/passport-card.png');

const SKY_BACKGROUND = '#bfeaf4';
const SKY_STROKE = '#87cfe1';

const PROFILE_IMAGE_STORAGE_KEY = 'adventour_profile_image';
const PROFILE_IMAGES = [
  { id: 'charley', label: 'Charley', source: require('../src/assets/profile/charley.jpg') },
  { id: 'dom', label: 'Dom', source: require('../src/assets/profile/dom.jpg') },
  { id: 'eric', label: 'Eric', source: require('../src/assets/profile/eric.jpg') },
  { id: 'nicnac', label: 'Nicnac', source: require('../src/assets/profile/nicnac.jpg') },
  { id: 'ryan', label: 'Ryan', source: require('../src/assets/profile/ryan.jpg') },
  { id: 'wanyea', label: 'Wanyea', source: require('../src/assets/profile/wanyea.jpg') },
];

type HistoryPlace = {
  place_id: number;
  provider?: string;
  provider_place_id?: string;
  name: string;
  latitude?: number;
  longitude?: number;
  category?: 'food' | 'activity';
  event_type: 'accept' | 'reject';
  occurred_at?: string;
  types: string[];
  vicinity?: string;
  photo_url?: string;
  photo_attributions?: any[];
  rating?: number;
  user_ratings_total?: number;
  price_level?: number;
};

type ProfilePayload = {
  user: {
    id: number;
    username?: string;
    display_name?: string;
    preferences: string[];
  };
  places: HistoryPlace[];
};

const formatDate = (value?: string) => {
  if (!value) {
    return '';
  }
  return new Date(value).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
};

const formatDuration = (seconds?: number) => {
  const totalMinutes = Math.max(0, Math.floor((seconds || 0) / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${Math.max(1, totalMinutes)}m`;
};

const backendPhotoUrl = (photoUrl?: string) => {
  if (!photoUrl) {
    return undefined;
  }
  return photoUrl.startsWith('http') ? photoUrl : `${Config.BACKEND_BASE_URL}${photoUrl}`;
};

const formatTagLabel = (tag: string) =>
  tag
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

const ProfileScreen: React.FC = () => {
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [adventours, setAdventours] = useState<AdventourSession[]>([]);
  const [selectedProfileImageId, setSelectedProfileImageId] = useState(PROFILE_IMAGES[0].id);
  const [profilePickerOpen, setProfilePickerOpen] = useState(false);

  useEffect(() => {
    const loadProfileImage = async () => {
      const stored = await AsyncStorage.getItem(PROFILE_IMAGE_STORAGE_KEY);
      if (stored && PROFILE_IMAGES.some((image) => image.id === stored)) {
        setSelectedProfileImageId(stored);
      }
    };

    loadProfileImage();
  }, []);

  const loadProfile = useCallback(async (isRefresh = false) => {
    if (isRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }
    setError(null);

    try {
      const [profileResponse, adventoursResponse] = await Promise.all([
        axios.get(`${Config.BACKEND_BASE_URL}/api/profile/history`, {
          params: {
            event_type: 'accept',
            limit: 50,
          },
        }),
        axios.get(`${Config.BACKEND_BASE_URL}/api/adventours/history`, {
          params: { limit: 12 },
        }),
      ]);
      setProfile(profileResponse.data);
      setAdventours(adventoursResponse.data.adventours || []);
    } catch (profileError) {
      console.error('Error loading profile history:', profileError);
      setError('Unable to load your Adventour profile yet.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      loadProfile();
    }, [loadProfile]),
  );

  if (loading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator />
        <Text style={styles.muted}>Loading profile...</Text>
      </View>
    );
  }

  const likedPlaces = profile?.places || [];
  const completedAdventours = adventours.filter((adventour) => adventour.status === 'completed');
  const displayName = profile?.user.display_name || profile?.user.username || 'Adventourer';
  const selectedProfileImage = PROFILE_IMAGES.find((image) => image.id === selectedProfileImageId) || PROFILE_IMAGES[0];
  const topAcceptedTags = Array.from(
    likedPlaces.reduce((tagCounts, place) => {
      (place.types || []).forEach((type) => {
        if (!type) {
          return;
        }
        tagCounts.set(type, (tagCounts.get(type) || 0) + 1);
      });
      return tagCounts;
    }, new Map<string, number>()),
  )
    .sort((first, second) => second[1] - first[1] || first[0].localeCompare(second[0]))
    .slice(0, 3)
    .map(([tag]) => tag);

  const chooseProfileImage = async (imageId: string) => {
    setSelectedProfileImageId(imageId);
    setProfilePickerOpen(false);
    await AsyncStorage.setItem(PROFILE_IMAGE_STORAGE_KEY, imageId);
  };

  const toPlace = (item: HistoryPlace): Place => ({
      place_id: String(item.place_id),
      provider: item.provider,
      provider_place_id: item.provider_place_id,
      name: item.name,
      vicinity: item.vicinity || (item.latitude && item.longitude
        ? `${item.latitude.toFixed(4)}, ${item.longitude.toFixed(4)}`
        : 'Saved Adventour place'),
      types: item.types || [],
      category: item.category,
      photo_url: backendPhotoUrl(item.photo_url),
      photo_attributions: item.photo_attributions || [],
      rating: item.rating,
      user_ratings_total: item.user_ratings_total,
      price_level: item.price_level,
  });

  const openHistoryPlace = async (item: HistoryPlace) => {
    const snapshot = toPlace(item);
    setSelectedPlace(snapshot);

    if (snapshot.photo_url && snapshot.rating) {
      return;
    }

    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/places/details`, {
        params: {
          place_id: item.place_id,
          provider: item.provider,
          provider_place_id: item.provider_place_id,
        },
      });
      const detail = response.data;
      setSelectedPlace({
        ...snapshot,
        name: detail.name || snapshot.name,
        vicinity: detail.vicinity || snapshot.vicinity,
        types: detail.types || snapshot.types,
        photo_url: backendPhotoUrl(detail.photo_url) || snapshot.photo_url,
        photo_attributions: detail.photo_attributions || snapshot.photo_attributions,
        rating: detail.rating ?? snapshot.rating,
        user_ratings_total: detail.user_ratings_total ?? snapshot.user_ratings_total,
        price_level: detail.price_level ?? snapshot.price_level,
      });
    } catch (detailsError) {
      console.error('Error loading place details:', detailsError);
    }
  };

  return (
    <View style={styles.container}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => loadProfile(true)} />
        }
      >
        <View style={styles.passportCover}>
          <ImageBackground source={passportCard} style={styles.passportArtwork} imageStyle={styles.passportArtworkImage} resizeMode="stretch">
            <Text style={styles.passportStamp}>PASSPORT</Text>
            <View style={styles.header}>
              <TouchableOpacity style={styles.avatar} activeOpacity={0.82} onPress={() => setProfilePickerOpen((open) => !open)}>
                <Image source={selectedProfileImage.source} style={styles.avatarImage} />
              </TouchableOpacity>
              <View style={styles.headerText}>
                <Text style={styles.name}>{displayName}</Text>
                <Text style={styles.passportMeta}>{likedPlaces.length} liked place{likedPlaces.length === 1 ? '' : 's'} stamped</Text>
                <Text style={styles.passportMeta}>{completedAdventours.length} completed Adventour{completedAdventours.length === 1 ? '' : 's'}</Text>
                <TouchableOpacity onPress={() => setProfilePickerOpen((open) => !open)}>
                  <Text style={styles.changePhotoText}>Change passport photo</Text>
                </TouchableOpacity>
              </View>
            </View>
          </ImageBackground>
          {profilePickerOpen ? (
            <View style={styles.profilePicker}>
              {PROFILE_IMAGES.map((image) => {
                const selected = image.id === selectedProfileImageId;
                return (
                  <TouchableOpacity
                    key={image.id}
                    style={[styles.profileOption, selected && styles.profileOptionSelected]}
                    onPress={() => chooseProfileImage(image.id)}
                  >
                    <Image source={image.source} style={styles.profileOptionImage} />
                  </TouchableOpacity>
                );
              })}
            </View>
          ) : null}
        </View>

        {topAcceptedTags.length ? (
          <View style={styles.tagPanel}>
            <Text style={styles.tagPanelTitle}>Top accepted tags</Text>
            <View style={styles.tagRow}>
              {topAcceptedTags.map((tag) => (
                <Text key={tag} style={styles.tag}>{formatTagLabel(tag)}</Text>
              ))}
            </View>
          </View>
        ) : null}

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Adventours</Text>
        </View>

        {completedAdventours.length ? (
          completedAdventours.slice(0, 3).map((adventour) => (
            <View key={adventour.id} style={styles.adventourCard}>
              <View style={styles.cardTopRow}>
                <Text style={styles.adventourTitle}>{adventour.title}</Text>
                <Text style={styles.dateText}>{formatDate(adventour.ended_at)}</Text>
              </View>
              <Text style={styles.adventourMeta}>
                {adventour.summary?.stop_count || 0} stops - {formatDuration(adventour.summary?.duration_seconds)}
              </Text>
              <Text style={styles.typeText} numberOfLines={2}>
                {adventour.stops
                  .filter((stop) => stop.status === 'completed')
                  .slice(0, 4)
                  .map((stop) => stop.display?.name || 'A stop')
                  .join(' -> ')}
              </Text>
            </View>
          ))
        ) : (
          <View style={styles.emptyJourneyCard}>
            <Text style={styles.emptyTitle}>No completed Adventours yet.</Text>
            <Text style={styles.muted}>Start one on Discover, finish a few stops, and the recap will live here.</Text>
          </View>
        )}

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Recently liked</Text>
          <TouchableOpacity onPress={() => loadProfile(true)}>
            <Text style={styles.refreshText}>Refresh</Text>
          </TouchableOpacity>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        {likedPlaces.length ? (
          likedPlaces.map((item) => (
            <TouchableOpacity key={String(item.place_id)} style={styles.placeCard} activeOpacity={0.82} onPress={() => openHistoryPlace(item)}>
              <View style={styles.cardTopRow}>
                <Text style={styles.placeName}>{item.name}</Text>
                <Text style={styles.dateText}>{formatDate(item.occurred_at)}</Text>
              </View>
              <Text style={styles.categoryText}>{item.category || 'saved place'}</Text>
              {item.types?.length ? (
                <Text style={styles.typeText} numberOfLines={1}>{item.types.slice(0, 4).join(', ')}</Text>
              ) : null}
              <Text style={styles.detailPrompt}>Tap for details</Text>
            </TouchableOpacity>
          ))
        ) : (
          <View style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>No liked places yet.</Text>
            <Text style={styles.muted}>Accept recommendations from Discover and they will show up here.</Text>
          </View>
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
  container: {
    flex: 1,
    backgroundColor: SKY_BACKGROUND,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 18,
    paddingBottom: 28,
  },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  passportCover: {
    marginBottom: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: SKY_STROKE,
    shadowColor: '#0b2551',
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.18,
    shadowRadius: 10,
    elevation: 4,
  },
  passportArtwork: {
    aspectRatio: 330 / 248,
    paddingHorizontal: 28,
    paddingTop: 66,
    paddingBottom: 54,
    justifyContent: 'center',
  },
  passportArtworkImage: {
    borderRadius: 12,
  },
  passportStamp: {
    position: 'absolute',
    left: 30,
    top: 34,
    color: '#1d66c0',
    borderColor: '#1d66c0',
    borderWidth: 2,
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 4,
    fontSize: 12,
    fontWeight: '900',
    transform: [{ rotate: '-5deg' }],
  },
  avatar: {
    width: 74,
    height: 74,
    borderRadius: 37,
    backgroundColor: '#baf3ff',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 14,
    overflow: 'hidden',
    borderWidth: 3,
    borderColor: '#1d66c0',
  },
  avatarImage: {
    width: 74,
    height: 74,
  },
  headerText: {
    flex: 1,
  },
  name: {
    fontSize: 23,
    fontWeight: '900',
    color: '#0e315c',
  },
  passportMeta: {
    color: '#1d66c0',
    fontWeight: '800',
  },
  changePhotoText: {
    color: '#ff4b47',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 6,
  },
  profilePicker: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: -8,
    paddingHorizontal: 10,
    paddingVertical: 10,
    backgroundColor: '#ffffff',
    borderWidth: 1,
    borderColor: SKY_STROKE,
    borderBottomLeftRadius: 8,
    borderBottomRightRadius: 8,
  },
  profileOption: {
    width: 42,
    height: 42,
    borderRadius: 21,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  profileOptionSelected: {
    borderColor: '#ff9f1c',
  },
  profileOptionImage: {
    width: 42,
    height: 42,
  },
  muted: {
    color: '#6b7280',
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  tagPanel: {
    marginBottom: 18,
  },
  tagPanelTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  tag: {
    backgroundColor: '#dff6f2',
    color: '#123c69',
    borderWidth: 1,
    borderColor: SKY_STROKE,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    overflow: 'hidden',
    fontWeight: '700',
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '900',
    color: '#123c69',
  },
  refreshText: {
    color: '#e6534b',
    fontWeight: '800',
  },
  error: {
    color: '#dc2626',
    marginBottom: 10,
  },
  placeCard: {
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: SKY_STROKE,
    padding: 14,
    marginBottom: 10,
  },
  adventourCard: {
    backgroundColor: '#123c69',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: SKY_STROKE,
    padding: 14,
    marginBottom: 10,
  },
  adventourTitle: {
    flex: 1,
    color: '#fff7ed',
    fontSize: 16,
    fontWeight: '900',
  },
  adventourMeta: {
    marginTop: 6,
    color: '#ff9f1c',
    fontWeight: '900',
  },
  emptyJourneyCard: {
    backgroundColor: '#dff6f2',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: SKY_STROKE,
    padding: 14,
    marginBottom: 14,
  },
  cardTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  placeName: {
    flex: 1,
    fontSize: 17,
    fontWeight: '900',
    color: '#123c69',
  },
  dateText: {
    color: '#6b7280',
    fontWeight: '700',
  },
  categoryText: {
    marginTop: 6,
    textTransform: 'capitalize',
    color: '#e6534b',
    fontWeight: '800',
  },
  typeText: {
    marginTop: 4,
    color: '#6b7280',
  },
  detailPrompt: {
    marginTop: 8,
    color: '#123c69',
    fontWeight: '800',
    fontSize: 12,
  },
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 8,
    borderWidth: 1,
    borderColor: SKY_STROKE,
    padding: 18,
    alignItems: 'center',
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: '900',
    color: '#123c69',
    marginBottom: 6,
  },
});

export default ProfileScreen;
