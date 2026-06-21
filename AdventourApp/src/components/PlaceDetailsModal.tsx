import React from 'react';
import {
  Image,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Place } from '../types/Place';
import Icon from 'react-native-vector-icons/MaterialCommunityIcons';

type Props = {
  place: Place | null;
  visible: boolean;
  onClose: () => void;
};

export const StarRating = ({ rating, size = 18 }: { rating?: number; size?: number }) => {
  const rounded = rating ? Math.round(rating) : 0;
  return (
    <View style={styles.starsRow}>
      {[1, 2, 3, 4, 5].map((star) => (
        <Text
          key={star}
          style={[
            styles.star,
            { fontSize: size },
            star <= rounded && styles.filledStar,
          ]}
        >
          ★
        </Text>
      ))}
    </View>
  );
};

const TravelTimes = ({ place }: { place: Place }) => {
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
        <View key={label} style={styles.travelPill}>
          <Icon name={icon} size={15} color="#123c69" accessibilityLabel={label} />
          <Text style={styles.travelText}>{minutes} min</Text>
        </View>
      ))}
    </View>
  );
};

const PlaceDetailsModal: React.FC<Props> = ({ place, visible, onClose }) => {
  if (!place) {
    return null;
  }

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <ScrollView showsVerticalScrollIndicator={false}>
            {place.photo_url ? (
              <Image source={{ uri: place.photo_url }} style={styles.heroImage} resizeMode="cover" />
            ) : (
              <View style={styles.heroPlaceholder}>
                <Text style={styles.heroPlaceholderText}>{place.category || 'Adventour'}</Text>
              </View>
            )}

            <Text style={styles.name}>{place.name}</Text>
            <Text style={styles.vicinity}>{place.vicinity}</Text>

            <View style={styles.ratingRow}>
              <StarRating rating={place.rating} size={20} />
              <Text style={styles.ratingText}>
                {place.rating ? place.rating.toFixed(1) : 'No rating'}
                {place.user_ratings_total ? ` (${place.user_ratings_total} reviews)` : ''}
              </Text>
            </View>
            <TravelTimes place={place} />

            <View style={styles.metaRow}>
              {place.category ? <Text style={styles.pill}>{place.category}</Text> : null}
              {place.price_level ? <Text style={styles.pill}>{'$'.repeat(place.price_level)}</Text> : null}
              {place.relevance !== undefined ? (
                <Text style={styles.pill}>Match {(place.relevance * 100).toFixed(0)}%</Text>
              ) : null}
            </View>

            {place.explanation ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Why this showed up</Text>
                <Text style={styles.bodyText}>{place.explanation}</Text>
              </View>
            ) : null}

            {place.types?.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Signals</Text>
                <Text style={styles.bodyText}>{place.types.slice(0, 8).join(', ')}</Text>
              </View>
            ) : null}
          </ScrollView>

          <TouchableOpacity style={styles.closeButton} onPress={onClose}>
            <Text style={styles.closeButtonText}>Close</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(17, 24, 39, 0.45)',
  },
  sheet: {
    maxHeight: '88%',
    backgroundColor: '#fff',
    borderTopLeftRadius: 16,
    borderTopRightRadius: 16,
    padding: 16,
  },
  handle: {
    alignSelf: 'center',
    width: 42,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#d1d5db',
    marginBottom: 12,
  },
  heroImage: {
    width: '100%',
    height: 210,
    borderRadius: 8,
    backgroundColor: '#e5e7eb',
    marginBottom: 14,
  },
  heroPlaceholder: {
    height: 150,
    borderRadius: 8,
    backgroundColor: '#eef2ff',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 14,
  },
  heroPlaceholderText: {
    color: '#3730a3',
    fontWeight: '900',
    textTransform: 'capitalize',
  },
  name: {
    fontSize: 26,
    lineHeight: 31,
    fontWeight: '900',
    color: '#111827',
    marginBottom: 6,
  },
  vicinity: {
    color: '#4b5563',
    fontSize: 15,
    lineHeight: 21,
    marginBottom: 12,
  },
  ratingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  starsRow: {
    flexDirection: 'row',
  },
  star: {
    color: '#d1d5db',
    marginRight: 1,
  },
  filledStar: {
    color: '#f59e0b',
  },
  ratingText: {
    color: '#374151',
    fontWeight: '700',
  },
  travelRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 12,
  },
  travelPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: '#eef2ff',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  travelText: {
    color: '#3730a3',
    fontWeight: '800',
  },
  travelIcon: {
    fontSize: 13,
  },
  metaRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 8,
  },
  pill: {
    backgroundColor: '#f3f4f6',
    color: '#374151',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 999,
    overflow: 'hidden',
    fontWeight: '800',
    textTransform: 'capitalize',
  },
  section: {
    marginTop: 16,
  },
  sectionTitle: {
    color: '#111827',
    fontWeight: '900',
    marginBottom: 6,
  },
  bodyText: {
    color: '#4b5563',
    lineHeight: 21,
  },
  closeButton: {
    marginTop: 14,
    backgroundColor: '#111827',
    borderRadius: 8,
    paddingVertical: 13,
    alignItems: 'center',
  },
  closeButtonText: {
    color: '#fff',
    fontWeight: '900',
  },
});

export default PlaceDetailsModal;
