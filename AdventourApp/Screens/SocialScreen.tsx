import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import axios from 'axios';
import Config from '../src/Config';
import AnimatedClouds from '../src/components/AnimatedClouds';

const wordmark = require('../src/assets/brand/adventour-wordmark.png');
const balloon = require('../src/assets/brand/adventour-balloon.png');

const SKY_BACKGROUND = '#bfeaf4';
const SKY_STROKE = '#87cfe1';
const NAVY = '#123c69';
const ORANGE = '#ff9f1c';
const RED = '#ff4b47';

const profileImages = {
  wanyea: require('../src/assets/profile/wanyea.jpg'),
  nicnac: require('../src/assets/profile/nicnac.jpg'),
  charley: require('../src/assets/profile/charley.jpg'),
  dom: require('../src/assets/profile/dom.jpg'),
  eric: require('../src/assets/profile/eric.jpg'),
  ryan: require('../src/assets/profile/ryan.jpg'),
  profpic_cheetah: require('../src/assets/profile/profpic_cheetah.png'),
  profpic_monkey: require('../src/assets/profile/profpic_monkey.png'),
  profpic_elephant: require('../src/assets/profile/profpic_elephant.png'),
  profpic_ladybug: require('../src/assets/profile/profpic_ladybug.png'),
  profpic_penguin: require('../src/assets/profile/profpic_penguin.png'),
  profpic_fox: require('../src/assets/profile/profpic_fox.png'),
};

type ProfileImageId = keyof typeof profileImages;

interface Person {
  id: number;
  username: string;
  display_name: string;
  profile_picture?: string;
  friendship_status?: string | null;
}

interface Friend extends Person {
  friendship_id: number;
  friendship_date: string;
}

interface FriendRequest extends Person {
  friendship_id: number;
  user_id: number;
  request_date: string;
}

interface FriendAdventour {
  id: number;
  title: string;
  ended_at?: string;
  stop_count: number;
  owner?: Person;
  summary?: {
    duration_seconds?: number;
    stop_count?: number;
    destination?: string;
    route_readiness?: {
      label?: string;
      score?: number;
    };
    destination_scout?: {
      selected_destination?: {
        label?: string;
      };
      rank?: {
        trip_readiness_score?: number;
        authenticity_score?: number;
      };
      explanation?: {
        headline?: string;
      };
    };
    local_events?: {
      status?: string;
      summary?: {
        event_count?: number;
        route_match_count?: number;
        reservation_ready_count?: number;
        route_reservation_ready_count?: number;
        top_event_title?: string | null;
        top_route_event_title?: string | null;
      };
      events?: {
        title?: string;
        reservation_url?: string | null;
      }[];
    };
    booking_plan?: {
      summary?: {
        readiness_score?: number;
      };
    };
    trip_packet?: {
      status?: string;
      booking_score?: number;
      headline?: string;
      booking_links?: {
        reservation_type?: string;
      }[];
      save_prompts?: {
        label?: string;
        reservation_type?: string;
      }[];
    };
    launch_checklist?: {
      can_start?: boolean;
      headline?: string;
    };
  };
}

type FriendAdventourBadge = {
  id: string;
  label: string;
  tone?: 'ready' | 'watch' | 'accent';
};

const profileSource = (id?: string) => {
  const imageId = id as ProfileImageId | undefined;
  return imageId && profileImages[imageId] ? profileImages[imageId] : profileImages.wanyea;
};

const formatDate = (value?: string) => {
  if (!value) {
    return 'recently';
  }
  return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};

const formatDuration = (seconds?: number) => {
  if (!seconds) {
    return 'freshly stamped';
  }
  const minutes = Math.max(1, Math.round(seconds / 60));
  if (minutes < 60) {
    return `${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
};

const percentLabel = (value?: number) => (
  typeof value === 'number' ? `${Math.round(value * 100)}%` : null
);

const friendAdventourBadges = (adventour: FriendAdventour): FriendAdventourBadge[] => {
  const summary = adventour.summary || {};
  const routePercent = percentLabel(summary.route_readiness?.score);
  const destinationPercent = percentLabel(summary.destination_scout?.rank?.trip_readiness_score);
  const bookingPercent = percentLabel(
    summary.trip_packet?.booking_score ?? summary.booking_plan?.summary?.readiness_score,
  );
  const eventSummary = summary.local_events?.summary || {};
  const eventCount = eventSummary.route_match_count ?? eventSummary.event_count ?? summary.local_events?.events?.length ?? 0;
  const reservationCount = eventSummary.route_reservation_ready_count ?? eventSummary.reservation_ready_count ?? 0;
  const savePromptCount = summary.trip_packet?.save_prompts?.length || 0;
  const badges: FriendAdventourBadge[] = [
    {
      id: 'stops',
      label: `${adventour.stop_count} stop${adventour.stop_count === 1 ? '' : 's'}`,
      tone: 'ready',
    },
    {
      id: 'duration',
      label: formatDuration(summary.duration_seconds),
    },
  ];

  if (routePercent) {
    badges.push({
      id: 'route',
      label: `${routePercent} route`,
      tone: (summary.route_readiness?.score || 0) >= 0.75 ? 'ready' : 'watch',
    });
  }
  if (summary.destination_scout?.selected_destination?.label) {
    badges.push({
      id: 'destination-scout',
      label: destinationPercent ? `${destinationPercent} trip pick` : 'Scout pick',
      tone: 'accent',
    });
  }
  if (eventCount) {
    badges.push({
      id: 'events',
      label: reservationCount ? `${reservationCount} RSVP` : `${eventCount} event${eventCount === 1 ? '' : 's'}`,
      tone: reservationCount ? 'accent' : 'watch',
    });
  }
  if (bookingPercent || savePromptCount) {
    badges.push({
      id: 'booking',
      label: savePromptCount ? `${savePromptCount} save prompt${savePromptCount === 1 ? '' : 's'}` : `${bookingPercent} booking`,
      tone: summary.trip_packet?.status === 'ready' ? 'ready' : 'watch',
    });
  }

  return badges.slice(0, 5);
};

const friendAdventourScoutNote = (adventour: FriendAdventour) => {
  const scout = adventour.summary?.destination_scout;
  const destination = scout?.selected_destination?.label || adventour.summary?.destination;
  if (!destination) {
    return null;
  }

  const headline = scout?.explanation?.headline;
  return headline
    ? `Trip scout picked ${destination}: ${headline}`
    : `Trip scout picked ${destination} for this Adventour.`;
};

const friendAdventourPreview = (adventour: FriendAdventour) => {
  const summary = adventour.summary || {};
  const eventSummary = summary.local_events?.summary || {};
  const eventTitle = eventSummary.top_route_event_title
    || eventSummary.top_event_title
    || summary.local_events?.events?.[0]?.title;
  if (eventTitle) {
    const reserveReady = Boolean(
      eventSummary.route_reservation_ready_count
      || eventSummary.reservation_ready_count
      || summary.local_events?.events?.some((event) => event.reservation_url),
    );
    return `${reserveReady ? 'Reservation-ready event' : 'Local event'}: ${eventTitle}`;
  }
  if (summary.trip_packet?.headline) {
    return summary.trip_packet.headline;
  }
  if (summary.route_readiness?.label) {
    return summary.route_readiness.label;
  }
  return summary.destination ? `Built for ${summary.destination}` : null;
};

const SocialScreen: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'friends' | 'adventours'>('friends');
  const [friends, setFriends] = useState<Friend[]>([]);
  const [friendRequests, setFriendRequests] = useState<FriendRequest[]>([]);
  const [friendAdventours, setFriendAdventours] = useState<FriendAdventour[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Person[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);

  const summaryText = useMemo(() => {
    if (activeTab === 'friends') {
      return `${friends.length} friend${friends.length === 1 ? '' : 's'} - ${friendRequests.length} request${friendRequests.length === 1 ? '' : 's'}`;
    }
    return `${friendAdventours.length} friend${friendAdventours.length === 1 ? '' : 's'}`;
  }, [activeTab, friendAdventours.length, friendRequests.length, friends.length]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [friendsResponse, requestsResponse, adventoursResponse] = await Promise.all([
        axios.get(`${Config.BACKEND_BASE_URL}/api/friends`),
        axios.get(`${Config.BACKEND_BASE_URL}/api/friends/requests`),
        axios.get(`${Config.BACKEND_BASE_URL}/api/friends/adventours`, { params: { limit: 20 } }),
      ]);
      setFriends(friendsResponse.data.friends || []);
      setFriendRequests(requestsResponse.data.requests || []);
      setFriendAdventours(adventoursResponse.data.adventours || []);
    } catch (error) {
      console.error('Error loading social data:', error);
      Alert.alert('Social unavailable', 'Adventour could not load friends and trips yet.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const searchUsers = async () => {
    const query = searchQuery.trim();
    if (query.length < 2) {
      setSearchResults([]);
      setSearched(false);
      return;
    }

    setSearching(true);
    setSearched(true);
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/friends/search`, {
        params: { q: query },
      });
      setSearchResults(response.data.users || []);
    } catch (error: any) {
      if (error?.response?.status === 400) {
        setSearchResults([]);
        return;
      }
      console.error('Error searching users:', error);
      Alert.alert('Search failed', 'Adventour could not search for that display name.');
    } finally {
      setSearching(false);
    }
  };

  const sendFriendRequest = async (friendId: number) => {
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/friends/request`, { friend_id: friendId });
      setSearchResults((current) => current.map((person) => (
        person.id === friendId ? { ...person, friendship_status: 'pending' } : person
      )));
      Alert.alert('Request sent', 'They will see your request in Friends & Trips.');
    } catch (error: any) {
      Alert.alert('Request failed', error.response?.data?.error || 'Could not send friend request.');
    }
  };

  const respondToFriendRequest = async (friendshipId: number, action: 'accept' | 'reject') => {
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/friends/respond`, {
        friendship_id: friendshipId,
        action,
      });
      await loadData();
    } catch (error: any) {
      Alert.alert('Request failed', error.response?.data?.error || 'Could not respond to request.');
    }
  };

  const takeFriendAdventour = async (adventour: FriendAdventour) => {
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/friends/adventours/${adventour.id}/take`);
      Alert.alert('Adventour saved', 'A draft is now active on Discover. End any active Adventour before taking another.');
    } catch (error: any) {
      Alert.alert('Could not take Adventour', error.response?.data?.error || 'Try again in a moment.');
    }
  };

  const renderPersonRow = (person: Person, action?: React.ReactNode) => (
    <View key={person.id} style={styles.personRow}>
      <Image source={profileSource(person.profile_picture)} style={styles.avatar} />
      <View style={styles.personText}>
        <Text style={styles.personName}>{person.display_name || person.username}</Text>
        <Text style={styles.personMeta}>@{person.username}</Text>
      </View>
      {action}
    </View>
  );

  return (
    <View style={styles.screen}>
      <ScrollView style={styles.scroll} contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <AnimatedClouds height={1100} speed="slow" />
        <View style={styles.foreground}>
          <View style={styles.heroCard}>
            <Image source={wordmark} style={styles.wordmark} resizeMode="contain" />
            <Text style={styles.kicker}>Friends & Trips</Text>
            <Text style={styles.title}>Find your travel people.</Text>
            <Text style={styles.subtitle}>{summaryText}</Text>
            <Image source={balloon} style={styles.balloon} resizeMode="contain" />
          </View>

          <View style={styles.tabs}>
            <TouchableOpacity
              style={[styles.tab, activeTab === 'friends' && styles.activeTab]}
              onPress={() => setActiveTab('friends')}
            >
              <Text style={[styles.tabText, activeTab === 'friends' && styles.activeTabText]}>Friends</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tab, activeTab === 'adventours' && styles.activeTab]}
              onPress={() => setActiveTab('adventours')}
            >
              <Text style={[styles.tabText, activeTab === 'adventours' && styles.activeTabText]}>Friend Adventours</Text>
            </TouchableOpacity>
          </View>

          <TouchableOpacity style={styles.primaryButton} onPress={() => setSearchOpen(true)} activeOpacity={0.86}>
            <Text style={styles.primaryButtonText}>Find by display name</Text>
          </TouchableOpacity>

          {loading ? (
            <View style={styles.loadingBox}>
              <ActivityIndicator color={NAVY} />
              <Text style={styles.emptyText}>Checking your travel circle...</Text>
            </View>
          ) : activeTab === 'friends' ? (
            <>
              {friendRequests.length ? (
                <View style={styles.section}>
                  <Text style={styles.sectionTitle}>Passport requests</Text>
                  {friendRequests.map((request) => (
                    <View key={request.friendship_id} style={styles.requestCard}>
                      {renderPersonRow(request)}
                      <View style={styles.requestActions}>
                        <TouchableOpacity
                          style={[styles.smallButton, styles.acceptButton]}
                          onPress={() => respondToFriendRequest(request.friendship_id, 'accept')}
                        >
                          <Text style={styles.smallButtonText}>Accept</Text>
                        </TouchableOpacity>
                        <TouchableOpacity
                          style={[styles.smallButton, styles.rejectButton]}
                          onPress={() => respondToFriendRequest(request.friendship_id, 'reject')}
                        >
                          <Text style={styles.smallButtonText}>Reject</Text>
                        </TouchableOpacity>
                      </View>
                    </View>
                  ))}
                </View>
              ) : null}

              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Your friends</Text>
                {friends.length ? friends.map((friend) => (
                  <View key={friend.id} style={styles.card}>
                    {renderPersonRow(friend)}
                    <Text style={styles.cardFootnote}>Friends since {formatDate(friend.friendship_date)}</Text>
                  </View>
                )) : (
                  <View style={styles.emptyCard}>
                    <Text style={styles.emptyTitle}>No passport pals yet.</Text>
                    <Text style={styles.emptyText}>Search a unique display name to send your first request.</Text>
                  </View>
                )}
              </View>
            </>
          ) : (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Adventours friends have taken</Text>
              {friendAdventours.length ? friendAdventours.map((adventour) => {
                const badges = friendAdventourBadges(adventour);
                const preview = friendAdventourPreview(adventour);
                const scoutNote = friendAdventourScoutNote(adventour);
                return (
                  <View key={adventour.id} style={styles.adventourCard}>
                    <View style={styles.adventourHeader}>
                      <Image source={profileSource(adventour.owner?.profile_picture)} style={styles.avatar} />
                      <View style={styles.personText}>
                        <Text style={styles.personName}>{adventour.title}</Text>
                        <Text style={styles.personMeta}>
                          by {adventour.owner?.display_name || 'a friend'} - {formatDate(adventour.ended_at)}
                        </Text>
                      </View>
                    </View>
                    <View style={styles.statsRow}>
                      {badges.map((badge) => (
                        <Text
                          key={badge.id}
                          style={[
                            styles.statPill,
                            badge.tone === 'ready' && styles.statPillReady,
                            badge.tone === 'watch' && styles.statPillWatch,
                            badge.tone === 'accent' && styles.statPillAccent,
                          ]}
                        >
                          {badge.label}
                        </Text>
                      ))}
                    </View>
                    {preview ? (
                      <Text style={styles.adventourPreview} numberOfLines={2}>
                        {preview}
                      </Text>
                    ) : null}
                    {scoutNote ? (
                      <Text style={styles.adventourScoutNote} numberOfLines={2}>
                        {scoutNote}
                      </Text>
                    ) : null}
                    <TouchableOpacity style={styles.takeButton} onPress={() => takeFriendAdventour(adventour)}>
                      <Text style={styles.takeButtonText}>Take Adventour</Text>
                    </TouchableOpacity>
                  </View>
                );
              }) : (
                <View style={styles.emptyCard}>
                  <Text style={styles.emptyTitle}>No friend Adventours yet.</Text>
                  <Text style={styles.emptyText}>When friends finish trips, their shared routes will show up here.</Text>
                </View>
              )}
            </View>
          )}
        </View>
      </ScrollView>

      <Modal visible={searchOpen} animationType="slide" onRequestClose={() => setSearchOpen(false)}>
        <View style={styles.modalScreen}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Find a friend</Text>
            <TouchableOpacity onPress={() => setSearchOpen(false)}>
              <Text style={styles.closeText}>Close</Text>
            </TouchableOpacity>
          </View>
          <Text style={styles.modalHelp}>Search their unique Adventour display name.</Text>
          <View style={styles.searchRow}>
            <TextInput
              style={styles.searchInput}
              placeholder="Display name"
              value={searchQuery}
              onChangeText={(text) => {
                setSearchQuery(text);
                setSearched(false);
              }}
              autoCapitalize="words"
              autoCorrect={false}
              onSubmitEditing={searchUsers}
            />
            <TouchableOpacity style={styles.searchButton} onPress={searchUsers}>
              {searching ? <ActivityIndicator color="#fffaf3" /> : <Text style={styles.searchButtonText}>Search</Text>}
            </TouchableOpacity>
          </View>

          <ScrollView contentContainerStyle={styles.searchResults}>
            {searchResults.map((person) => renderPersonRow(
              person,
              <TouchableOpacity
                style={[styles.addButton, person.friendship_status === 'pending' && styles.addButtonDisabled]}
                onPress={() => sendFriendRequest(person.id)}
                disabled={person.friendship_status === 'pending' || person.friendship_status === 'accepted'}
              >
                <Text style={styles.addButtonText}>
                  {person.friendship_status === 'accepted'
                    ? 'Friends'
                    : person.friendship_status === 'pending'
                      ? 'Pending'
                      : 'Add'}
                </Text>
              </TouchableOpacity>,
            ))}
            {searched && !searching && searchResults.length === 0 ? (
              <View style={styles.emptyCard}>
                <Text style={styles.emptyTitle}>No display name found.</Text>
                <Text style={styles.emptyText}>Check the spelling and try their exact Adventour name.</Text>
              </View>
            ) : null}
          </ScrollView>
        </View>
      </Modal>
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: SKY_BACKGROUND,
  },
  scroll: {
    flex: 1,
  },
  content: {
    padding: 14,
    paddingBottom: 30,
    position: 'relative',
  },
  foreground: {
    zIndex: 1,
  },
  heroCard: {
    backgroundColor: '#d9f8fb',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 210,
    overflow: 'hidden',
    padding: 16,
    shadowColor: NAVY,
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  wordmark: {
    height: 62,
    marginBottom: -15,
    marginLeft: -5,
    marginTop: -16,
    width: 130,
  },
  kicker: {
    color: RED,
    fontSize: 12,
    fontWeight: '900',
    letterSpacing: 0.6,
    marginTop: 9,
    textTransform: 'uppercase',
  },
  title: {
    color: NAVY,
    fontSize: 27,
    fontWeight: '900',
    lineHeight: 31,
    marginTop: 6,
    paddingRight: 110,
  },
  subtitle: {
    color: '#31506b',
    fontSize: 13,
    fontWeight: '800',
    marginTop: 8,
  },
  balloon: {
    bottom: 10,
    height: 137,
    position: 'absolute',
    right: 18,
    width: 98,
  },
  tabs: {
    backgroundColor: '#dff6f2',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    marginTop: 12,
    padding: 4,
  },
  tab: {
    alignItems: 'center',
    borderRadius: 7,
    flex: 1,
    paddingVertical: 11,
  },
  activeTab: {
    backgroundColor: NAVY,
  },
  tabText: {
    color: NAVY,
    fontSize: 13,
    fontWeight: '900',
  },
  activeTabText: {
    color: '#fffaf3',
  },
  primaryButton: {
    alignItems: 'center',
    alignSelf: 'stretch',
    backgroundColor: NAVY,
    borderColor: ORANGE,
    borderRadius: 999,
    borderWidth: 2,
    marginTop: 12,
    paddingVertical: 13,
  },
  primaryButtonText: {
    color: '#fffaf3',
    fontSize: 14,
    fontWeight: '900',
  },
  loadingBox: {
    alignItems: 'center',
    padding: 20,
  },
  section: {
    marginTop: 16,
  },
  sectionTitle: {
    color: NAVY,
    fontSize: 18,
    fontWeight: '900',
    marginBottom: 10,
  },
  card: {
    backgroundColor: '#fffaf3',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    padding: 12,
  },
  requestCard: {
    backgroundColor: '#fffaf3',
    borderColor: ORANGE,
    borderRadius: 8,
    borderWidth: 2,
    marginBottom: 10,
    padding: 12,
  },
  personRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
  avatar: {
    backgroundColor: '#dff6f2',
    borderColor: NAVY,
    borderRadius: 24,
    borderWidth: 2,
    height: 48,
    marginRight: 11,
    width: 48,
  },
  personText: {
    flex: 1,
  },
  personName: {
    color: NAVY,
    fontSize: 15,
    fontWeight: '900',
  },
  personMeta: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '800',
    marginTop: 2,
  },
  cardFootnote: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 9,
  },
  requestActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  smallButton: {
    alignItems: 'center',
    borderRadius: 999,
    flex: 1,
    paddingVertical: 9,
  },
  acceptButton: {
    backgroundColor: NAVY,
  },
  rejectButton: {
    backgroundColor: RED,
  },
  smallButtonText: {
    color: '#fffaf3',
    fontSize: 13,
    fontWeight: '900',
  },
  adventourCard: {
    backgroundColor: '#fffaf3',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 12,
    padding: 13,
  },
  adventourHeader: {
    alignItems: 'center',
    flexDirection: 'row',
  },
  statsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 12,
  },
  statPill: {
    backgroundColor: '#dff6f2',
    borderColor: SKY_STROKE,
    borderRadius: 999,
    borderWidth: 1,
    color: NAVY,
    fontSize: 12,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  statPillReady: {
    backgroundColor: NAVY,
    borderColor: NAVY,
    color: '#fffaf3',
  },
  statPillWatch: {
    backgroundColor: '#fff7ed',
    borderColor: ORANGE,
    color: '#9a3412',
  },
  statPillAccent: {
    backgroundColor: '#fee2e2',
    borderColor: RED,
    color: '#991b1b',
  },
  adventourPreview: {
    backgroundColor: '#e8f8fb',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 17,
    marginTop: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  adventourScoutNote: {
    backgroundColor: '#fff7ed',
    borderColor: ORANGE,
    borderRadius: 8,
    borderWidth: 1,
    color: NAVY,
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 8,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  takeButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: ORANGE,
    borderColor: NAVY,
    borderRadius: 999,
    borderWidth: 2,
    marginTop: 12,
    paddingHorizontal: 14,
    paddingVertical: 9,
  },
  takeButtonText: {
    color: NAVY,
    fontSize: 13,
    fontWeight: '900',
  },
  emptyCard: {
    backgroundColor: '#dff6f2',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    padding: 16,
  },
  emptyTitle: {
    color: NAVY,
    fontSize: 16,
    fontWeight: '900',
  },
  emptyText: {
    color: '#6b7280',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 19,
    marginTop: 5,
  },
  modalScreen: {
    backgroundColor: SKY_BACKGROUND,
    flex: 1,
    paddingTop: 52,
  },
  modalHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 18,
  },
  modalTitle: {
    color: NAVY,
    fontSize: 24,
    fontWeight: '900',
  },
  closeText: {
    color: RED,
    fontSize: 14,
    fontWeight: '900',
  },
  modalHelp: {
    color: '#31506b',
    fontSize: 13,
    fontWeight: '800',
    marginHorizontal: 18,
    marginTop: 8,
  },
  searchRow: {
    flexDirection: 'row',
    gap: 9,
    margin: 18,
  },
  searchInput: {
    backgroundColor: '#fff',
    borderColor: SKY_STROKE,
    borderRadius: 8,
    borderWidth: 1,
    color: NAVY,
    flex: 1,
    fontSize: 16,
    fontWeight: '700',
    paddingHorizontal: 12,
  },
  searchButton: {
    alignItems: 'center',
    backgroundColor: NAVY,
    borderRadius: 8,
    justifyContent: 'center',
    minWidth: 88,
    paddingHorizontal: 13,
  },
  searchButtonText: {
    color: '#fffaf3',
    fontSize: 13,
    fontWeight: '900',
  },
  searchResults: {
    padding: 18,
    paddingTop: 0,
  },
  addButton: {
    backgroundColor: NAVY,
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  addButtonDisabled: {
    backgroundColor: '#7aa6bd',
  },
  addButtonText: {
    color: '#fffaf3',
    fontSize: 12,
    fontWeight: '900',
  },
});

export default SocialScreen;
