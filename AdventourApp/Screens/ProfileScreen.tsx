import React, { useCallback, useEffect, useState } from 'react';
import {
  Alert,
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
import axios from 'axios';
import Config from '../src/Config';
import PlaceDetailsModal from '../src/components/PlaceDetailsModal';
import { Place } from '../src/types/Place';
import { AdventourSession, AdventourStop } from '../src/types/Adventour';
import { tagGroupIdsForPlace, tagGroupMeta } from '../src/placeTagGroups';
import AuthService from '../src/services/AuthService';
import { User } from '../src/services/AuthService';

const passportCard = require('../src/assets/profile/passport-card.png');
const ticketCard = require('../src/assets/cards/ticket-card.png');
const stampCard = require('../src/assets/cards/stamp-card.png');

const SKY_BACKGROUND = '#bfeaf4';
const SKY_STROKE = '#87cfe1';
const PASSPORT_STAMP_INK = '#172033';

const PROFILE_IMAGES = [
  { id: 'wanyea', label: 'Wanyea', source: require('../src/assets/profile/wanyea.jpg') },
  { id: 'nicnac', label: 'Nicnac', source: require('../src/assets/profile/nicnac.jpg') },
  { id: 'charley', label: 'Charley', source: require('../src/assets/profile/charley.jpg') },
  { id: 'dom', label: 'Dom', source: require('../src/assets/profile/dom.jpg') },
  { id: 'eric', label: 'Eric', source: require('../src/assets/profile/eric.jpg') },
  { id: 'ryan', label: 'Ryan', source: require('../src/assets/profile/ryan.jpg') },
  { id: 'profpic_cheetah', label: 'Cheetah', source: require('../src/assets/profile/profpic_cheetah.png') },
  { id: 'profpic_monkey', label: 'Monkey', source: require('../src/assets/profile/profpic_monkey.png') },
  { id: 'profpic_elephant', label: 'Elephant', source: require('../src/assets/profile/profpic_elephant.png') },
  { id: 'profpic_ladybug', label: 'Ladybug', source: require('../src/assets/profile/profpic_ladybug.png') },
  { id: 'profpic_penguin', label: 'Penguin', source: require('../src/assets/profile/profpic_penguin.png') },
  { id: 'profpic_fox', label: 'Fox', source: require('../src/assets/profile/profpic_fox.png') },
];

type ProfileScreenProps = {
  onSignOut?: () => void | Promise<void>;
  onAccountDeleted?: () => void | Promise<void>;
  onUserUpdated?: (user: User) => void;
};

type HistoryPlace = {
  event_id?: number;
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
    profile_picture?: string;
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

const completedStopsForAdventour = (adventour: AdventourSession) =>
  adventour.stops.filter((stop) => stop.status === 'completed');

const routePinsForStops = (stops: AdventourStop[]) => {
  const stopsWithCoordinates = stops.filter((stop) => (
    typeof stop.display?.latitude === 'number' && typeof stop.display?.longitude === 'number'
  ));

  if (!stopsWithCoordinates.length) {
    return [];
  }

  const latitudes = stopsWithCoordinates.map((stop) => stop.display.latitude as number);
  const longitudes = stopsWithCoordinates.map((stop) => stop.display.longitude as number);
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const latitudeRange = Math.max(maxLatitude - minLatitude, 0.001);
  const longitudeRange = Math.max(maxLongitude - minLongitude, 0.001);

  return stopsWithCoordinates.map((stop, index) => ({
    id: stop.id,
    label: String(index + 1),
    name: stop.display?.name || `Stop ${index + 1}`,
    x: 12 + (((stop.display.longitude as number) - minLongitude) / longitudeRange) * 76,
    y: 88 - (((stop.display.latitude as number) - minLatitude) / latitudeRange) * 76,
  }));
};

const cityCountryFromAddress = (address?: string) => {
  if (!address) {
    return null;
  }

  const parts = address.split(',').map((part) => part.trim()).filter(Boolean);
  if (!parts.length) {
    return null;
  }

  return {
    city: parts.length >= 3 ? parts[parts.length - 3] : parts[0],
    country: parts[parts.length - 1],
  };
};

const ProfileScreen: React.FC<ProfileScreenProps> = ({ onSignOut, onAccountDeleted, onUserUpdated }) => {
  const [profile, setProfile] = useState<ProfilePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [adventours, setAdventours] = useState<AdventourSession[]>([]);
  const [selectedProfileImageId, setSelectedProfileImageId] = useState(PROFILE_IMAGES[0].id);
  const [profilePickerOpen, setProfilePickerOpen] = useState(false);
  const [resettingAccount, setResettingAccount] = useState(false);

  useEffect(() => {
    const profilePicture = profile?.user.profile_picture;
    if (profilePicture && PROFILE_IMAGES.some((image) => image.id === profilePicture)) {
      setSelectedProfileImageId(profilePicture);
    }
  }, [profile?.user.profile_picture]);

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
  const visitedAddresses = [
    ...likedPlaces.map((place) => place.vicinity),
    ...completedAdventours.flatMap((adventour) => (
      completedStopsForAdventour(adventour).map((stop) => stop.display?.vicinity)
    )),
  ];
  const visitedLocations = visitedAddresses
    .map(cityCountryFromAddress)
    .filter((location): location is { city: string; country: string } => Boolean(location));
  const visitedCities = new Set(visitedLocations.map((location) => location.city));
  const visitedCountries = new Set(visitedLocations.map((location) => location.country));
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
    const previousImageId = selectedProfileImageId;
    setSelectedProfileImageId(imageId);
    setProfilePickerOpen(false);

    try {
      const updatedUser = await AuthService.updateProfile({ profile_picture: imageId });
      onUserUpdated?.(updatedUser);
      setProfile((currentProfile) => currentProfile ? {
        ...currentProfile,
        user: {
          ...currentProfile.user,
          profile_picture: updatedUser.profile_picture,
        },
      } : currentProfile);
    } catch (profileError) {
      console.error('Error saving profile image:', profileError);
      setSelectedProfileImageId(previousImageId);
      Alert.alert('Unable to save photo', 'Your profile photo could not be saved. Please try again.');
    }
  };

  const handleSignOut = async () => {
    if (onSignOut) {
      await onSignOut();
      return;
    }

    await AuthService.signOut();
  };

  const handleResetAccount = () => {
    Alert.alert(
      'Reset Adventour profile?',
      'This deletes your Adventour profile, history, ratings, and active trips from the local backend, then removes your Firebase login so you can sign up again with the same email.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Reset',
          style: 'destructive',
          onPress: async () => {
            setResettingAccount(true);
            try {
              await AuthService.deleteAccount();
              if (onAccountDeleted) {
                await onAccountDeleted();
              }
            } catch (resetError: any) {
              console.error('Error resetting account:', resetError);
              const message = resetError?.code === 'auth/requires-recent-login'
                ? 'Firebase needs a fresh login before deleting this account. Sign out, sign back in, and try reset again.'
                : 'Your Adventour profile could not be reset. Please try again.';
              Alert.alert('Reset failed', message);
            } finally {
              setResettingAccount(false);
            }
          },
        },
      ],
    );
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
            <View style={styles.passportStamp}>
              <View style={styles.passportStampBorder}>
                <Text style={styles.passportStampTop}>ADVENTOUR</Text>
                <View style={styles.passportStampBand} />
                <Text style={styles.passportStampBottom}>PASSPORT</Text>
              </View>
            </View>
            <View style={styles.header}>
              <TouchableOpacity style={styles.avatar} activeOpacity={0.82} onPress={() => setProfilePickerOpen((open) => !open)}>
                <Image source={selectedProfileImage.source} style={styles.avatarImage} />
              </TouchableOpacity>
              <View style={styles.headerText}>
                <Text style={styles.name}>{displayName}</Text>
                <Text style={styles.passportMeta}>{likedPlaces.length} liked place{likedPlaces.length === 1 ? '' : 's'} stamped</Text>
                <Text style={styles.passportMeta}>{completedAdventours.length} completed Adventour{completedAdventours.length === 1 ? '' : 's'}</Text>
                {visitedCities.size || visitedCountries.size ? (
                  <Text style={styles.passportMeta}>
                    {visitedCities.size} cit{visitedCities.size === 1 ? 'y' : 'ies'} - {visitedCountries.size} countr{visitedCountries.size === 1 ? 'y' : 'ies'}
                  </Text>
                ) : null}
                <TouchableOpacity onPress={() => setProfilePickerOpen((open) => !open)}>
                  <Text style={styles.changePhotoText}>Change passport photo</Text>
                </TouchableOpacity>
                {onSignOut ? (
                  <TouchableOpacity onPress={handleSignOut}>
                    <Text style={styles.signOutText}>Sign out</Text>
                  </TouchableOpacity>
                ) : null}
                {onSignOut ? (
                  <TouchableOpacity onPress={handleResetAccount} disabled={resettingAccount}>
                    <Text style={[styles.resetAccountText, resettingAccount && styles.disabledText]}>
                      {resettingAccount ? 'Resetting...' : 'Reset profile'}
                    </Text>
                  </TouchableOpacity>
                ) : null}
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
          completedAdventours.slice(0, 3).map((adventour) => {
            const completedStops = completedStopsForAdventour(adventour);
            const routePins = routePinsForStops(completedStops);

            return (
              <ImageBackground
                key={adventour.id}
                source={ticketCard}
                style={styles.ticketCard}
                imageStyle={styles.ticketCardImage}
                resizeMode="stretch"
              >
                <View style={styles.ticketContent}>
                  <View style={styles.cardTopRow}>
                    <Text style={styles.ticketKicker}>Boarding pass</Text>
                    <Text style={styles.ticketDate}>{formatDate(adventour.ended_at)}</Text>
                  </View>
                  <Text style={styles.adventourTitle}>{adventour.title}</Text>
                  <Text style={styles.adventourMeta}>
                    {adventour.summary?.stop_count || 0} stops - {formatDuration(adventour.summary?.duration_seconds)}
                  </Text>

                  <View style={styles.routeMap}>
                    <View style={[styles.mapGridLine, styles.mapGridLineOne]} />
                    <View style={[styles.mapGridLine, styles.mapGridLineTwo]} />
                    <View style={[styles.mapGridLineVertical, styles.mapGridLineThree]} />
                    <View style={[styles.mapGridLineVertical, styles.mapGridLineFour]} />
                    {routePins.length ? (
                      routePins.map((pin) => (
                        <View
                          key={pin.id}
                          style={[
                            styles.routePin,
                            { left: `${pin.x}%`, top: `${pin.y}%` },
                          ]}
                        >
                          <Text style={styles.routePinText}>{pin.label}</Text>
                        </View>
                      ))
                    ) : (
                      <Text style={styles.routeMapEmpty}>Route pins will appear when stops have coordinates.</Text>
                    )}
                  </View>

                  <Text style={styles.routeStopsText} numberOfLines={2}>
                    {completedStops
                      .slice(0, 4)
                      .map((stop) => stop.display?.name || 'A stop')
                      .join(' -> ')}
                  </Text>
                </View>
              </ImageBackground>
            );
          })
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
          likedPlaces.map((item, itemIndex) => (
            <TouchableOpacity
              key={item.event_id ? `liked-event-${item.event_id}` : `liked-place-${item.place_id}-${item.occurred_at || itemIndex}`}
              activeOpacity={0.82}
              onPress={() => openHistoryPlace(item)}
            >
              {/*
                Use Adventour tag groups instead of legacy food/activity lanes so
                the Passport reflects the same taste language as Discover.
              */}
              <ImageBackground
                source={stampCard}
                style={styles.stampCard}
                imageStyle={styles.stampCardImage}
                resizeMode="stretch"
              >
                <View style={styles.placeStampMark}>
                  <Text style={styles.placeStampText}>LIKED</Text>
                  <Text style={styles.placeStampDate}>{formatDate(item.occurred_at)}</Text>
                </View>
                <View style={styles.stampContent}>
                  <Text style={styles.placeName} numberOfLines={1}>{item.name}</Text>
                  <View style={styles.placeTagRow}>
                    {tagGroupIdsForPlace({
                      name: item.name,
                      types: item.types || [],
                      user_ratings_total: item.user_ratings_total,
                    }).slice(0, 3).map((groupId, groupIndex) => {
                      const group = tagGroupMeta(groupId);
                      return (
                        <Text
                          key={`${item.event_id || item.place_id}-${groupId}-${groupIndex}`}
                          style={[
                            styles.placeTag,
                            {
                              backgroundColor: group?.backgroundColor || '#dff6f2',
                              color: group?.color || '#123c69',
                              borderColor: group?.color || SKY_STROKE,
                            },
                          ]}
                        >
                          {group ? `${group.emoji} ${group.label}` : groupId}
                        </Text>
                      );
                    })}
                  </View>
                  <Text style={styles.detailPrompt}>Tap for details</Text>
                </View>
              </ImageBackground>
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
    left: 20,
    top: 42,
    width: 84,
    height: 48,
    alignItems: 'center',
    justifyContent: 'center',
    transform: [{ rotate: '-11deg' }],
    opacity: 0.92,
  },
  passportStampBorder: {
    width: '100%',
    height: '100%',
    borderWidth: 2,
    borderColor: PASSPORT_STAMP_INK,
    borderStyle: 'dashed',
    backgroundColor: 'rgba(255, 255, 255, 0.18)',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  passportStampTop: {
    position: 'absolute',
    top: 5,
    color: PASSPORT_STAMP_INK,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.6,
  },
  passportStampBand: {
    width: 61,
    height: 11,
    backgroundColor: PASSPORT_STAMP_INK,
    transform: [{ rotate: '-8deg' }],
  },
  passportStampBottom: {
    position: 'absolute',
    bottom: 5,
    color: PASSPORT_STAMP_INK,
    fontSize: 8,
    fontWeight: '900',
    letterSpacing: 0.6,
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
  signOutText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 4,
  },
  resetAccountText: {
    color: '#ff4b47',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 4,
  },
  disabledText: {
    opacity: 0.5,
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
  ticketCard: {
    aspectRatio: 4 / 3,
    marginBottom: 12,
    paddingHorizontal: 23,
    paddingVertical: 22,
  },
  ticketCardImage: {
    borderRadius: 8,
  },
  ticketContent: {
    flex: 1,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  ticketKicker: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  ticketDate: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '800',
  },
  adventourTitle: {
    color: '#123c69',
    fontSize: 16,
    fontWeight: '900',
    marginTop: 3,
  },
  adventourMeta: {
    marginTop: 6,
    color: '#e6534b',
    fontWeight: '900',
  },
  routeMap: {
    backgroundColor: '#dff6f2',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    height: 118,
    marginTop: 10,
    overflow: 'hidden',
    position: 'relative',
  },
  mapGridLine: {
    backgroundColor: 'rgba(18, 60, 105, 0.12)',
    height: 1,
    left: 0,
    position: 'absolute',
    right: 0,
  },
  mapGridLineVertical: {
    backgroundColor: 'rgba(18, 60, 105, 0.12)',
    bottom: 0,
    position: 'absolute',
    top: 0,
    width: 1,
  },
  mapGridLineOne: {
    top: '34%',
  },
  mapGridLineTwo: {
    top: '67%',
  },
  mapGridLineThree: {
    left: '35%',
  },
  mapGridLineFour: {
    left: '69%',
  },
  routePin: {
    alignItems: 'center',
    backgroundColor: '#ff4b47',
    borderColor: '#fffaf3',
    borderRadius: 11,
    borderWidth: 2,
    height: 22,
    justifyContent: 'center',
    marginLeft: -11,
    marginTop: -11,
    position: 'absolute',
    shadowColor: '#0b2551',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
    width: 22,
  },
  routePinText: {
    color: '#fffaf3',
    fontSize: 10,
    fontWeight: '900',
  },
  routeMapEmpty: {
    alignSelf: 'center',
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 43,
    paddingHorizontal: 18,
    textAlign: 'center',
  },
  routeStopsText: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 7,
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
  stampCard: {
    aspectRatio: 330 / 186,
    marginBottom: 10,
    paddingHorizontal: 26,
    paddingVertical: 22,
  },
  stampCardImage: {
    borderRadius: 8,
  },
  stampContent: {
    flex: 1,
    justifyContent: 'center',
    paddingRight: 58,
  },
  placeTagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 7,
  },
  placeTag: {
    borderRadius: 999,
    borderWidth: 1,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  placeStampMark: {
    alignItems: 'center',
    borderColor: '#e6534b',
    borderRadius: 999,
    borderStyle: 'dashed',
    borderWidth: 2,
    height: 54,
    justifyContent: 'center',
    opacity: 0.84,
    position: 'absolute',
    right: 28,
    top: 23,
    transform: [{ rotate: '-12deg' }],
    width: 54,
  },
  placeStampText: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
  },
  placeStampDate: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '800',
    marginTop: 1,
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
