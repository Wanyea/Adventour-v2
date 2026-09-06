import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  AppState,
  Dimensions,
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
import { useIsFocused } from '@react-navigation/native';

type Props = {
  places: Place[];
  activeFilterLabel: string;
  totalPlaces: number;
  loadingMore?: boolean;
  canLoadMore?: boolean;
  onFeedback: (place: Place, verdict: 'accept' | 'reject') => Promise<void>;
  onImpression?: (place: Place) => Promise<void>;
  onOpenPlace: (place: Place) => void;
  onExhausted?: () => void;
};

const loadedPhotoUrls = new Set<string>();

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
      <PlaceImage place={place} fallbackLabel={primaryLabel} />
      <Text style={[styles.name, muted && styles.mutedText]} numberOfLines={2}>
        {place.name}
      </Text>
      <Text style={styles.vicinity} numberOfLines={2}>
        {place.vicinity}
      </Text>
      <TravelTimes place={place} muted={muted} />
      <View style={styles.scoreRow}>
        {place.relevance !== undefined ? (
          <Text style={styles.score}>Index {place.relevance.toFixed(3)}</Text>
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
  totalPlaces,
  loadingMore,
  canLoadMore,
  onFeedback,
  onImpression,
  onOpenPlace,
  onExhausted,
}) => {
  const position = useRef(new Animated.ValueXY()).current;
  const promote = useRef(new Animated.Value(1)).current;
  const currentPlace = places[0];
  const cardRef = useRef<View>(null);
  const focused = useIsFocused();
  const [foreground, setForeground] = useState(AppState.currentState === 'active');
  useEffect(() => {
    const subscription = AppState.addEventListener('change', (state) => setForeground(state === 'active'));
    return () => subscription.remove();
  }, []);
  const feedbackPending = useRef(false);
  const nextPlace = places[1];
  const allResultsExhausted = totalPlaces === 0;

  useEffect(() => {
    if (!currentPlace || !focused || !foreground || !onImpression) { return; }
    let sent = false;
    const timer = setInterval(() => {
      if (sent) { return; }
      cardRef.current?.measureInWindow((_x, y, _width, height) => {
        const visible = Math.max(0, Math.min(y + height, Dimensions.get('window').height) - Math.max(y, 0));
        if (height > 0 && visible >= height / 2) {
          sent = true;
          onImpression(currentPlace).then(() => clearInterval(timer)).catch(() => { sent = false; });
        }
      });
    }, 700);
    return () => clearInterval(timer);
  }, [currentPlace, focused, foreground, onImpression]);

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
    if (!currentPlace || feedbackPending.current) {
      return;
    }

    feedbackPending.current = true;
    const x = verdict === 'accept' ? 520 : -520;
    Animated.timing(position, {
      toValue: { x, y: 0 },
      duration: 180,
      useNativeDriver: false,
    }).start(async () => {
      try { await onFeedback(currentPlace, verdict); }
      finally {
        position.setValue({ x: 0, y: 0 });
        feedbackPending.current = false;
      }
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
            ref={cardRef}
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
    marginBottom: 10,
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
