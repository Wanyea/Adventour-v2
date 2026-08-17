import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  Image,
  PanResponder,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Place } from '../types/Place';
import { StarRating } from './PlaceDetailsModal';
import { tagGroupDisplayLabel, tagGroupMeta } from '../placeTagGroups';
import Icon from 'react-native-vector-icons/MaterialCommunityIcons';

type Props = {
  places: Place[];
  activeFilterLabel: string;
  partyLabel?: string;
  totalPlaces: number;
  loadingMore?: boolean;
  canLoadMore?: boolean;
  onFeedback: (place: Place, verdict: 'accept' | 'reject') => void;
  onOpenPlace: (place: Place) => void;
  onExhausted?: () => void;
};

const loadedPhotoUrls = new Set<string>();

const scoutProfileMeta = (profile?: string) => {
  switch (profile) {
    case 'authenticity_forward':
      return {
        label: 'Hidden gems scout',
        icon: 'diamond-stone',
        tone: '#e6534b',
        backgroundColor: '#fff7ed',
      };
    case 'group_friendly':
      return {
        label: 'Group fit scout',
        icon: 'account-heart',
        tone: '#4c1d95',
        backgroundColor: '#f3e8ff',
      };
    case 'fresh_discovery':
      return {
        label: 'Fresh finds scout',
        icon: 'map-marker-star',
        tone: '#134e4a',
        backgroundColor: '#dff6f2',
      };
    case 'event_anchor':
      return {
        label: 'Event anchor scout',
        icon: 'calendar-star',
        tone: '#0f4c81',
        backgroundColor: '#e0f2fe',
      };
    default:
      return null;
  }
};

const PlaceImage = ({ place, fallbackLabel }: { place: Place; fallbackLabel: string }) => {
  const [loaded, setLoaded] = useState(Boolean(place.photo_url && loadedPhotoUrls.has(place.photo_url)));

  useEffect(() => {
    setLoaded(Boolean(place.photo_url && loadedPhotoUrls.has(place.photo_url)));
  }, [place.photo_url]);

  if (!place.photo_url) {
    return (
      <View style={styles.imagePlaceholder}>
        <Text style={styles.imagePlaceholderText}>{fallbackLabel}</Text>
      </View>
    );
  }

  return (
    <View style={styles.imageWrap}>
      {!loaded && (
        <View style={styles.imageLoading}>
          <Text style={styles.imagePlaceholderText}>Loading photo</Text>
        </View>
      )}
      <Image
        source={{ uri: place.photo_url }}
        style={[styles.placeImage, !loaded && styles.hiddenImage]}
        resizeMode="cover"
        onLoadEnd={() => {
          if (place.photo_url) {
            loadedPhotoUrls.add(place.photo_url);
          }
          setLoaded(true);
        }}
      />
    </View>
  );
};

const TravelTimes = ({ place, muted = false }: { place: Place; muted?: boolean }) => {
  const times = place.travel_times;
  if (!times) {
    return null;
  }

  const items = [
    { label: 'Walk', icon: 'walk', minutes: times.walk_minutes },
    { label: 'Car', icon: 'car', minutes: times.drive_minutes },
    { label: 'Train', icon: 'train', minutes: times.transit_minutes },
  ].filter((item): item is { label: string; icon: string; minutes: number } => typeof item.minutes === 'number');

  if (!items.length) {
    return null;
  }

  return (
    <View style={styles.travelRow}>
      {items.map(({ label, icon, minutes }) => (
        <View key={label} style={[styles.travelPill, muted && styles.mutedTravelPill]}>
          <Icon
            name={icon}
            size={14}
            color={muted ? '#6b7280' : '#123c69'}
            accessibilityLabel={label}
          />
          <Text style={[styles.travelText, muted && styles.mutedTravelText]}>
            {minutes} min
          </Text>
        </View>
      ))}
    </View>
  );
};

const recommendationSignal = (place: Place) => {
  const likedBy = place.history?.friend_liked_by || [];
  const rejectedBy = place.history?.friend_rejected_by || [];
  const friendHistoryFit = place.score_components?.friend_history_fit || 0;

  if (likedBy.length && friendHistoryFit > 0) {
    return {
      label: `Liked by ${likedBy.slice(0, 2).join(', ')}`,
      icon: 'account-heart',
      tone: '#4c1d95',
      backgroundColor: '#f3e8ff',
    };
  }

  if (rejectedBy.length && friendHistoryFit < 0) {
    return {
      label: `Passed by ${rejectedBy.slice(0, 2).join(', ')}`,
      icon: 'account-alert',
      tone: '#9a3412',
      backgroundColor: '#fff7ed',
    };
  }

  if (place.repeat_after_exhaustion) {
    if (place.history?.rejected) {
      return {
        label: 'Exhausted repeat',
        icon: 'refresh-alert',
        tone: '#9a3412',
        backgroundColor: '#fff7ed',
      };
    }
    return {
      label: 'Worth another look',
      icon: 'refresh',
      tone: '#31506b',
      backgroundColor: '#e8f8fb',
    };
  }

  if ((place.score_components?.repeat_penalty || 0) > 0 || (place.history?.recent_impressions || 0) > 0) {
    return {
      label: 'Seen recently',
      icon: 'history',
      tone: '#31506b',
      backgroundColor: '#e8f8fb',
    };
  }

  if (
    (place.score_components?.exploration_applied || 0) > 0
    && place.ranking?.exploration_budget?.allowed
  ) {
    if (place.ranking.exploration_budget.friend_learning) {
      const friendName = place.ranking.exploration_budget.served_learning_members?.[0];
      return {
        label: friendName ? `Learning ${friendName}` : 'Friend learning',
        icon: 'account-heart-outline',
        tone: '#123c69',
        backgroundColor: '#e8f8fb',
      };
    }

    return {
      label: 'Learning pick',
      icon: 'school-outline',
      tone: '#123c69',
      backgroundColor: '#e8f8fb',
    };
  }

  if (place.local_event_match) {
    return {
      label: place.local_event_match.title ? 'Event nearby' : 'Event-backed',
      icon: 'calendar-star',
      tone: '#e6534b',
      backgroundColor: '#fff7ed',
    };
  }

  if (place.ranking?.party_coverage_rescue) {
    return {
      label: place.ranking.rescued_member ? `For ${place.ranking.rescued_member}` : 'Friend match',
      icon: 'account-multiple-heart',
      tone: '#4c1d95',
      backgroundColor: '#f3e8ff',
    };
  }

  if (place.ranking?.local_discovery_rescue) {
    return {
      label: 'Local discovery',
      icon: 'map-marker-star-outline',
      tone: '#e6534b',
      backgroundColor: '#fff7ed',
    };
  }

  if ((place.score_components?.value_gem || 0) >= 0.6) {
    return {
      label: 'Value gem',
      icon: 'ticket-percent-outline',
      tone: '#0f766e',
      backgroundColor: '#dcfce7',
    };
  }

  if ((place.score_components?.novelty || 0) >= 0.9) {
    return {
      label: 'Fresh pick',
      icon: 'sparkles',
      tone: '#134e4a',
      backgroundColor: '#dff6f2',
    };
  }

  if (place.authenticity_evidence?.label === 'Hidden gem') {
    return {
      label: 'Hidden gem',
      icon: 'diamond-stone',
      tone: '#e6534b',
      backgroundColor: '#fff7ed',
    };
  }

  if (place.authenticity_evidence?.label === 'Local-feeling') {
    return {
      label: 'Local-feeling',
      icon: 'store-marker',
      tone: '#134e4a',
      backgroundColor: '#dff6f2',
    };
  }

  if ((place.ranking?.member_coverage_bonus || 0) > 0) {
    return {
      label: 'Helps party fit',
      icon: 'account-heart',
      tone: '#4c1d95',
      backgroundColor: '#f3e8ff',
    };
  }

  if ((place.ranking?.diversity_bonus || 0) > (place.ranking?.diversity_penalty || 0)) {
    return {
      label: 'Adds variety',
      icon: 'map-marker-star',
      tone: '#123c69',
      backgroundColor: '#e8f8fb',
    };
  }

  return null;
};

const groupFitSummary = (place: Place) => {
  const backendSummary = place.party_fit_summary;
  if (backendSummary?.members?.length && backendSummary.members.length > 1) {
    return {
      averageFit: backendSummary.average_fit ?? backendSummary.group_fit ?? 0,
      label: backendSummary.headline || 'Party fit',
      detail: backendSummary.detail,
      members: backendSummary.members.slice(0, 3),
    };
  }

  const members = (place.member_fit || [])
    .filter((member) => typeof member.fit === 'number')
    .sort((left, right) => right.fit - left.fit);

  if (members.length <= 1) {
    return null;
  }

  const averageFit = members.reduce((sum, member) => sum + member.fit, 0) / members.length;
  const helpedMembers = place.ranking?.party_coverage_rescue && place.ranking.rescued_member
    ? [place.ranking.rescued_member]
    : place.ranking?.served_new_members || [];
  const label = helpedMembers.length
    ? place.ranking?.party_coverage_rescue
      ? `Made room for ${helpedMembers.slice(0, 2).join(', ')}`
      : `Helps ${helpedMembers.slice(0, 2).join(', ')}`
    : averageFit >= 0.7
      ? 'Balanced for the party'
      : 'Mixed party fit';

  return {
    averageFit,
    label,
    detail: place.ranking?.party_coverage_rescue
      ? 'Included so this basket gives every traveler a strong match.'
      : undefined,
    members: members.slice(0, 3),
  };
};

const learnedRankSignal = (place: Place) => {
  const score = typeof place.learned_score === 'number'
    ? place.learned_score
    : place.ranking?.learned_model_score;

  if (typeof score !== 'number') {
    return null;
  }

  return {
    score,
    rank: place.learned_rank_position,
  };
};

const RecommendationStory = ({ place, muted = false }: { place: Place; muted?: boolean }) => {
  const story = place.recommendation_story;
  if (!story?.headline && !story?.reasons?.length && !story?.metrics?.length) {
    return null;
  }

  const reasons = story.reasons?.slice(0, 2) || [];
  const cautions = story.cautions?.slice(0, 1) || [];
  const metrics = (story.metrics || [])
    .filter((metric) => ['match', 'local_signal', 'party_fit', 'hidden_gem', 'local_proof', 'value_gem', 'learning', 'local_event', 'session_context', 'friend_history'].includes(metric.id))
    .slice(0, 3);

  return (
    <View style={[styles.storyBox, muted && styles.mutedStoryBox]}>
      <View style={styles.storyHeader}>
        <View style={styles.storyTitleRow}>
          <Icon name="compass-outline" size={14} color={muted ? '#6b7280' : '#123c69'} />
          <Text style={[styles.storyKicker, muted && styles.mutedStoryText]}>Why this pick</Text>
        </View>
        {story.authenticity_label ? (
          <Text style={[styles.storyBadge, muted && styles.mutedStoryBadge]} numberOfLines={1}>
            {story.authenticity_label}
          </Text>
        ) : null}
      </View>
      {story.headline ? (
        <Text style={[styles.storyHeadline, muted && styles.mutedStoryText]} numberOfLines={2}>
          {story.headline}
        </Text>
      ) : null}
      {metrics.length ? (
        <View style={styles.storyMetricRow}>
          {metrics.map((metric) => (
            <Text key={metric.id} style={[styles.storyMetricPill, muted && styles.mutedStoryMetricPill]}>
              {metric.label} {metric.display || ''}
            </Text>
          ))}
        </View>
      ) : null}
      {[...reasons, ...cautions].slice(0, 2).map((reason, index) => (
        <Text
          key={`${index}-${reason}`}
          style={[
            styles.storyReason,
            index >= reasons.length && styles.storyCaution,
            muted && styles.mutedStoryText,
          ]}
          numberOfLines={2}
        >
          {index >= reasons.length ? 'Watch: ' : ''}{reason}
        </Text>
      ))}
    </View>
  );
};

const CompactPlaceContent = ({
  place,
  fallbackLabel,
  muted = false,
}: {
  place: Place;
  fallbackLabel: string;
  muted?: boolean;
}) => {
  const tagLabels = (place.tag_groups || []).slice(0, 3).map(tagGroupDisplayLabel);
  const primaryGroup = tagGroupMeta((place.tag_groups || [])[0] || '');
  const primaryLabel = tagLabels[0] || fallbackLabel;
  const signal = recommendationSignal(place);
  const learnedSignal = learnedRankSignal(place);
  const scoutProfile = scoutProfileMeta(
    place.scoring_profile
    || place.score_components?.scoring_profile
    || place.ranking?.scoring_profile,
  );
  const partyFit = groupFitSummary(place);

  return (
    <>
      <View style={[styles.accentBar, { backgroundColor: primaryGroup?.color || '#0f766e' }]} />
      <View style={styles.tagRow}>
        {(place.tag_groups?.length ? place.tag_groups.slice(0, 3) : ['fallback']).map((groupId, index) => {
          const group = tagGroupMeta(groupId);
          const label = group ? `${group.emoji} ${group.label}` : primaryLabel;
          return (
            <Text
              key={`${groupId}-${index}`}
              style={[
                styles.categoryLabel,
                {
                  backgroundColor: group?.backgroundColor || '#ccfbf1',
                  color: group?.color || '#134e4a',
                },
                muted && styles.mutedCategoryLabel,
              ]}
            >
              {label}
            </Text>
          );
        })}
      </View>
      {signal ? (
        <View
          style={[
            styles.signalPill,
            {
              backgroundColor: signal.backgroundColor,
              borderColor: signal.tone,
            },
            muted && styles.mutedSignalPill,
          ]}
        >
          <Icon name={signal.icon} size={13} color={muted ? '#6b7280' : signal.tone} />
          <Text style={[styles.signalText, { color: muted ? '#6b7280' : signal.tone }]}>
            {signal.label}
          </Text>
        </View>
      ) : null}
      {learnedSignal ? (
        <View style={[styles.scoutPill, styles.learnedPill, muted && styles.mutedSignalPill]}>
          <Icon name="brain" size={13} color={muted ? '#6b7280' : '#123c69'} />
          <Text style={[styles.signalText, { color: muted ? '#6b7280' : '#123c69' }]}>
            Learned rank{learnedSignal.rank ? ` #${learnedSignal.rank}` : ''} - {Math.round(learnedSignal.score * 100)}%
          </Text>
        </View>
      ) : null}
      {scoutProfile ? (
        <View
          style={[
            styles.scoutPill,
            {
              backgroundColor: scoutProfile.backgroundColor,
              borderColor: scoutProfile.tone,
            },
            muted && styles.mutedSignalPill,
          ]}
        >
          <Icon name={scoutProfile.icon} size={13} color={muted ? '#6b7280' : scoutProfile.tone} />
          <Text style={[styles.signalText, { color: muted ? '#6b7280' : scoutProfile.tone }]}>
            {scoutProfile.label}
          </Text>
        </View>
      ) : null}
      {partyFit ? (
        <View style={[styles.groupFitCard, muted && styles.mutedGroupFitCard]}>
          <View style={styles.groupFitHeader}>
            <View style={styles.groupFitTitleRow}>
              <Icon name="account-group" size={14} color={muted ? '#6b7280' : '#4c1d95'} />
              <Text style={[styles.groupFitTitle, muted && styles.mutedGroupFitText]}>
                {partyFit.label}
              </Text>
            </View>
            <Text style={[styles.groupFitScore, muted && styles.mutedGroupFitText]}>
              {Math.round(partyFit.averageFit * 100)}%
            </Text>
          </View>
          <View style={styles.groupFitMembers}>
            {partyFit.members.map((member) => (
              <View key={member.user_id} style={[styles.groupFitPill, muted && styles.mutedGroupFitPill]}>
                <Text style={[styles.groupFitMemberName, muted && styles.mutedGroupFitText]} numberOfLines={1}>
                  {member.display_name}
                </Text>
                <Text style={[styles.groupFitMemberScore, muted && styles.mutedGroupFitText]}>
                  {Math.round(member.fit * 100)}%
                </Text>
              </View>
            ))}
          </View>
          {partyFit.detail ? (
            <Text style={[styles.groupFitDetail, muted && styles.mutedGroupFitText]} numberOfLines={2}>
              {partyFit.detail}
            </Text>
          ) : null}
        </View>
      ) : null}
      <PlaceImage place={place} fallbackLabel={primaryLabel} />
      <Text style={[styles.name, muted && styles.mutedText]} numberOfLines={2}>
        {place.name}
      </Text>
      <Text style={styles.vicinity} numberOfLines={2}>
        {place.vicinity}
      </Text>
      <TravelTimes place={place} muted={muted} />
      <RecommendationStory place={place} muted={muted} />
      <View style={styles.scoreRow}>
        {place.relevance !== undefined ? (
          <Text style={styles.score}>Match {(place.relevance * 100).toFixed(0)}%</Text>
        ) : <View />}
        <View style={styles.ratingRow}>
          <StarRating rating={place.rating} size={15} />
          <Text style={styles.detail}>
            {place.rating ? place.rating.toFixed(1) : 'N/A'}
            {place.user_ratings_total ? ` (${place.user_ratings_total})` : ''}
          </Text>
        </View>
      </View>
    </>
  );
};

const RecommendationDeck: React.FC<Props> = ({
  places,
  activeFilterLabel,
  partyLabel,
  totalPlaces,
  loadingMore,
  canLoadMore,
  onFeedback,
  onOpenPlace,
  onExhausted,
}) => {
  const position = useRef(new Animated.ValueXY()).current;
  const promote = useRef(new Animated.Value(1)).current;
  const currentPlace = places[0];
  const nextPlace = places[1];
  const allResultsExhausted = totalPlaces === 0;

  useEffect(() => {
    if (!currentPlace && canLoadMore && !loadingMore) {
      onExhausted?.();
    }
  }, [canLoadMore, currentPlace, loadingMore, onExhausted]);

  useEffect(() => {
    position.setValue({ x: 0, y: 0 });
    promote.setValue(0);
    Animated.timing(promote, {
      toValue: 1,
      duration: 140,
      useNativeDriver: false,
    }).start();
  }, [currentPlace?.place_id, position, promote]);

  const swipeCard = (verdict: 'accept' | 'reject') => {
    if (!currentPlace) {
      return;
    }

    const x = verdict === 'accept' ? 520 : -520;
    Animated.timing(position, {
      toValue: { x, y: 0 },
      duration: 180,
      useNativeDriver: false,
    }).start(() => {
      onFeedback(currentPlace, verdict);
      position.setValue({ x: 0, y: 0 });
    });
  };

  const cardPanResponder = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gesture) =>
          Math.abs(gesture.dx) > 12 && Math.abs(gesture.dx) > Math.abs(gesture.dy),
        onPanResponderMove: Animated.event(
          [null, { dx: position.x, dy: position.y }],
          { useNativeDriver: false },
        ),
        onPanResponderRelease: (_, gesture) => {
          if (gesture.dx > 110) {
            swipeCard('accept');
          } else if (gesture.dx < -110) {
            swipeCard('reject');
          } else {
            Animated.spring(position, {
              toValue: { x: 0, y: 0 },
              useNativeDriver: false,
            }).start();
          }
        },
      }),
    [currentPlace, position],
  );

  const rotate = position.x.interpolate({
    inputRange: [-220, 0, 220],
    outputRange: ['-8deg', '0deg', '8deg'],
    extrapolate: 'clamp',
  });

  const acceptOpacity = position.x.interpolate({
    inputRange: [40, 160],
    outputRange: [0, 1],
    extrapolate: 'clamp',
  });

  const rejectOpacity = position.x.interpolate({
    inputRange: [-160, -40],
    outputRange: [1, 0],
    extrapolate: 'clamp',
  });

  const activeScale = promote.interpolate({
    inputRange: [0, 1],
    outputRange: [0.96, 1],
  });

  const activeOpacity = promote.interpolate({
    inputRange: [0, 1],
    outputRange: [0.68, 1],
  });

  return (
    <View style={styles.container}>
      <View style={styles.basketHeader}>
        <View>
          <Text style={styles.basketTitle}>Basket picks</Text>
          <Text style={styles.hint}>{activeFilterLabel}: swipe right to accept, left to pass.</Text>
          {partyLabel ? (
            <Text style={styles.partyHint}>For {partyLabel}</Text>
          ) : null}
        </View>
        <Text style={styles.ticketCount}>{totalPlaces}</Text>
      </View>

      <View style={styles.deckArea}>
        {nextPlace && (
          <View style={[styles.card, styles.nextCard]}>
            <CompactPlaceContent place={nextPlace} fallbackLabel={activeFilterLabel} muted />
          </View>
        )}

        {currentPlace ? (
          <Animated.View
            style={[
              styles.card,
              styles.activeCard,
              {
                opacity: activeOpacity,
                transform: [
                  { translateX: position.x },
                  { translateY: position.y },
                  { scale: activeScale },
                  { rotate },
                ],
              },
            ]}
            {...cardPanResponder.panHandlers}
          >
            <Animated.Text style={[styles.swipeStamp, styles.rejectStamp, { opacity: rejectOpacity }]}>
              PASS
            </Animated.Text>
            <Animated.Text style={[styles.swipeStamp, styles.acceptStamp, { opacity: acceptOpacity }]}>
              ACCEPT
            </Animated.Text>

            <TouchableOpacity activeOpacity={0.92} onPress={() => onOpenPlace(currentPlace)}>
              <CompactPlaceContent place={currentPlace} fallbackLabel={activeFilterLabel} />
            </TouchableOpacity>

            <View style={styles.actions}>
              <TouchableOpacity style={[styles.actionButton, styles.passButton]} onPress={() => swipeCard('reject')}>
                <Text style={styles.passButtonText}>Pass</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.actionButton, styles.acceptButton]} onPress={() => swipeCard('accept')}>
                <Text style={styles.acceptButtonText}>Accept</Text>
              </TouchableOpacity>
            </View>
          </Animated.View>
        ) : (
          <View style={[styles.card, styles.emptyCard]}>
            {loadingMore ? (
              <>
                <ActivityIndicator color="#123c69" />
                <Text style={styles.emptyTitle}>Scouting more picks...</Text>
                <Text style={styles.emptyText}>The balloon is checking for another batch.</Text>
              </>
            ) : (
              <>
                <Text style={styles.emptyTitle}>
                  {allResultsExhausted
                    ? 'All caught up.'
                    : `No ${activeFilterLabel.toLowerCase()} picks in this batch.`}
                </Text>
                <Text style={styles.emptyText}>
                  {allResultsExhausted
                    ? 'Search again to load fresh recommendations.'
                    : 'Try another tag group or search again to load fresh recommendations.'}
                </Text>
              </>
            )}
          </View>
        )}
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: '#dff6f2',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#87cfe1',
  },
  basketHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
    paddingHorizontal: 2,
  },
  basketTitle: {
    color: '#123c69',
    fontSize: 16,
    fontWeight: '900',
  },
  hint: {
    color: '#31506b',
    fontSize: 12,
    marginTop: 1,
  },
  partyHint: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '800',
    marginTop: 2,
  },
  ticketCount: {
    minWidth: 32,
    textAlign: 'center',
    overflow: 'hidden',
    backgroundColor: '#e6534b',
    color: '#fff',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
    fontWeight: '900',
  },
  deckArea: {
    minHeight: 382,
    justifyContent: 'center',
  },
  card: {
    backgroundColor: '#fffdf8',
    borderRadius: 8,
    padding: 14,
    borderWidth: 1,
    borderColor: '#87cfe1',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.12,
    shadowRadius: 8,
    elevation: 4,
  },
  activeCard: {
    minHeight: 326,
    justifyContent: 'center',
  },
  nextCard: {
    position: 'absolute',
    left: 10,
    right: 10,
    minHeight: 306,
    opacity: 0.68,
    transform: [{ scale: 0.96 }],
  },
  accentBar: {
    height: 4,
    borderRadius: 999,
    marginBottom: 10,
  },
  tagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 7,
  },
  categoryLabel: {
    alignSelf: 'flex-start',
    backgroundColor: '#eef2ff',
    color: '#3730a3',
    fontWeight: '800',
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: 999,
    overflow: 'hidden',
  },
  mutedCategoryLabel: {
    backgroundColor: '#f3f4f6',
    color: '#6b7280',
  },
  signalPill: {
    alignSelf: 'flex-start',
    alignItems: 'center',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 4,
    marginBottom: 9,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  scoutPill: {
    alignSelf: 'flex-start',
    alignItems: 'center',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 4,
    marginBottom: 9,
    marginTop: -3,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  learnedPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#123c69',
  },
  mutedSignalPill: {
    opacity: 0.58,
  },
  signalText: {
    fontSize: 11,
    fontWeight: '900',
  },
  groupFitCard: {
    backgroundColor: '#f3e8ff',
    borderColor: '#c4b5fd',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    padding: 9,
  },
  mutedGroupFitCard: {
    backgroundColor: '#f9fafb',
    borderColor: '#e5e7eb',
  },
  groupFitHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
    marginBottom: 7,
  },
  groupFitTitleRow: {
    alignItems: 'center',
    flex: 1,
    flexDirection: 'row',
    gap: 5,
  },
  groupFitTitle: {
    color: '#4c1d95',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  groupFitScore: {
    color: '#4c1d95',
    fontSize: 12,
    fontWeight: '900',
  },
  groupFitMembers: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  groupFitPill: {
    alignItems: 'center',
    backgroundColor: '#fffdf8',
    borderColor: '#c4b5fd',
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 4,
    maxWidth: '100%',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  mutedGroupFitPill: {
    backgroundColor: '#fff',
    borderColor: '#e5e7eb',
  },
  groupFitMemberName: {
    color: '#4c1d95',
    fontSize: 11,
    fontWeight: '800',
    maxWidth: 112,
  },
  groupFitMemberScore: {
    color: '#4c1d95',
    fontSize: 11,
    fontWeight: '900',
  },
  groupFitDetail: {
    color: '#4c1d95',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 7,
  },
  mutedGroupFitText: {
    color: '#6b7280',
  },
  name: {
    fontSize: 22,
    lineHeight: 27,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 5,
  },
  mutedText: {
    color: '#4b5563',
  },
  placeImage: {
    width: '100%',
    height: 112,
    borderRadius: 8,
    backgroundColor: '#e5e7eb',
  },
  imageWrap: {
    width: '100%',
    height: 112,
    borderRadius: 8,
    marginBottom: 10,
    overflow: 'hidden',
    backgroundColor: '#fef3c7',
  },
  imageLoading: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff7ed',
  },
  hiddenImage: {
    opacity: 0,
  },
  imagePlaceholder: {
    width: '100%',
    height: 104,
    borderRadius: 8,
    marginBottom: 10,
    backgroundColor: '#fff7ed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imagePlaceholderText: {
    color: '#134e4a',
    fontWeight: '800',
  },
  vicinity: {
    fontSize: 14,
    color: '#4b5563',
    marginBottom: 7,
  },
  travelRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 9,
  },
  travelPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: '#f3f4f6',
    borderRadius: 999,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  mutedTravelPill: {
    backgroundColor: '#f9fafb',
  },
  travelText: {
    color: '#374151',
    fontSize: 11,
    fontWeight: '800',
  },
  mutedTravelText: {
    color: '#6b7280',
  },
  storyBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 9,
    padding: 9,
  },
  mutedStoryBox: {
    backgroundColor: '#f9fafb',
    borderColor: '#e5e7eb',
    opacity: 0.82,
  },
  storyHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  storyTitleRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 5,
  },
  storyKicker: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  storyBadge: {
    backgroundColor: '#fffdf8',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#e6534b',
    flexShrink: 1,
    fontSize: 9,
    fontWeight: '900',
    maxWidth: 112,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  mutedStoryBadge: {
    borderColor: '#d1d5db',
    color: '#6b7280',
  },
  storyHeadline: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
  },
  storyMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  storyMetricPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  mutedStoryMetricPill: {
    backgroundColor: '#fff',
    borderColor: '#e5e7eb',
    color: '#6b7280',
  },
  storyReason: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 5,
  },
  storyCaution: {
    color: '#9a3412',
  },
  mutedStoryText: {
    color: '#6b7280',
  },
  scoreRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 8,
  },
  score: {
    fontSize: 15,
    fontWeight: '800',
    color: '#e6534b',
  },
  detail: {
    fontSize: 13,
    color: '#374151',
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  actions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 14,
  },
  actionButton: {
    flex: 1,
    paddingVertical: 11,
    borderRadius: 8,
    alignItems: 'center',
    borderWidth: 1,
  },
  passButton: {
    backgroundColor: '#fff',
    borderColor: '#e6534b',
  },
  acceptButton: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
  },
  passButtonText: {
    color: '#e6534b',
    fontWeight: '800',
  },
  acceptButtonText: {
    color: '#fff',
    fontWeight: '800',
  },
  swipeStamp: {
    position: 'absolute',
    top: 24,
    zIndex: 2,
    borderWidth: 3,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 5,
    fontSize: 22,
    fontWeight: '900',
  },
  acceptStamp: {
    left: 18,
    color: '#123c69',
    borderColor: '#123c69',
    transform: [{ rotate: '-12deg' }],
  },
  rejectStamp: {
    right: 18,
    color: '#e6534b',
    borderColor: '#e6534b',
    transform: [{ rotate: '12deg' }],
  },
  emptyCard: {
    minHeight: 260,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: '#111827',
    marginBottom: 8,
  },
  emptyText: {
    color: '#6b7280',
    textAlign: 'center',
  },
});

export default RecommendationDeck;
