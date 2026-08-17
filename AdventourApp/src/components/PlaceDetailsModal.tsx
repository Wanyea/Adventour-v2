import React from 'react';
import {
  DimensionValue,
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

const formatEventDistance = (distance?: number | null) => {
  if (typeof distance !== 'number') {
    return 'nearby';
  }
  if (distance < 1000) {
    return `${Math.round(distance)}m away`;
  }
  return `${(distance / 1609.344).toFixed(1)} mi away`;
};

const recommendationSignals = (place: Place) => {
  const rows: { label: string; value: string }[] = [];
  const components = place.score_components || {};
  const history = place.history || {};
  const ranking = place.ranking || {};
  const authenticity = place.authenticity_evidence;
  const scoringProfile = place.scoring_profile || components.scoring_profile || ranking.scoring_profile;
  const likedBy = history.friend_liked_by || [];
  const rejectedBy = history.friend_rejected_by || [];
  const friendHistoryFit = components.friend_history_fit || 0;

  if (scoringProfile) {
    const profileCopy: Record<string, string> = {
      phase1_balanced: 'Balanced scout: weighs your taste, local feel, distance, timing, and variety together.',
      authenticity_forward: 'Hidden gems scout: gives extra lift to local-feeling, less generic places.',
      group_friendly: 'Group fit scout: gives more influence to friend fit and party balance.',
      fresh_discovery: 'Fresh finds scout: pushes harder toward variety and places you have not seen recently.',
      event_anchor: 'Event anchor scout: gives extra lift to timely local events, RSVP links, and social anchors nearby.',
      learned_beta: 'Learned beta: starts with the balanced scout, then lets the trained model rerank the basket.',
    };
    rows.push({
      label: 'Scout style',
      value: profileCopy[scoringProfile] || scoringProfile.replace(/_/g, ' '),
    });
  }

  const learnedScore = typeof place.learned_score === 'number'
    ? place.learned_score
    : ranking.learned_model_score;
  if (typeof learnedScore === 'number') {
    rows.push({
      label: 'Learned ranker',
      value: `${Math.round(learnedScore * 100)}% model score${place.learned_rank_position ? `, rank #${place.learned_rank_position}` : ''}${ranking.learned_model_type ? ` (${ranking.learned_model_type})` : ''}`,
    });
  }

  if (place.repeat_after_exhaustion) {
    rows.push({
      label: 'Repeat reason',
      value: history.rejected
        ? 'You passed before, but Adventour ran out of stronger nearby options.'
        : 'Adventour is repeating this because nearby options are exhausted.',
    });
  }

  if (typeof history.recent_impressions === 'number') {
    rows.push({
      label: 'Seen recently',
      value: `${history.recent_impressions} time${history.recent_impressions === 1 ? '' : 's'} in the last recommendation window`,
    });
  }

  if (typeof components.novelty === 'number') {
    rows.push({
      label: 'Freshness',
      value: `${Math.round(components.novelty * 100)}%`,
    });
  }

  if ((components.repeat_penalty || 0) > 0) {
    rows.push({
      label: 'Repeat penalty',
      value: `${Math.round((components.repeat_penalty || 0) * 100)} point nudge toward fresher places`,
    });
  }

  if ((components.decision_penalty || 0) > 0) {
    rows.push({
      label: 'Decision penalty',
      value: 'Lowered because you already accepted or passed on this place.',
    });
  }

  if (likedBy.length && friendHistoryFit > 0) {
    rows.push({
      label: 'Friend signal',
      value: `${likedBy.slice(0, 3).join(', ')} already liked or chose this place, so Adventour nudged it up for this group.`,
    });
  }

  if (rejectedBy.length && friendHistoryFit < 0) {
    rows.push({
      label: 'Friend caution',
      value: `${rejectedBy.slice(0, 3).join(', ')} passed on this place before, so Adventour lowered it for this group.`,
    });
  }

  if ((components.chain_penalty || 0) > 0) {
    rows.push({
      label: 'Chain penalty',
      value: 'Lowered because Adventour is prioritizing local-authentic picks.',
    });
  }

  if ((components.price_penalty || 0) > 0) {
    rows.push({
      label: 'Budget fit',
      value: 'Lowered because it is above the selected budget.',
    });
  } else if ((components.value_gem || 0) >= 0.6) {
    rows.push({
      label: 'Value gem',
      value: 'Lifted because it looks affordable without giving up local texture.',
    });
  }

  if (typeof components.time_fit === 'number') {
    rows.push({
      label: 'Timing fit',
      value: `${Math.round(components.time_fit * 100)}% match for the current time of day`,
    });
  }

  if ((components.time_penalty || 0) > 0) {
    rows.push({
      label: 'Timing penalty',
      value: 'Lowered because it is less ideal for the current time of day.',
    });
  }

  if (place.local_event_match) {
    const event = place.local_event_match;
    rows.push({
      label: 'Local event nearby',
      value: `${event.title || 'A local event'} is ${formatEventDistance(event.distance_to_place_meters)}${event.reservation_url ? ' and has a reservation link.' : event.source_url ? ' with a source link to verify.' : '.'}`,
    });
  }

  if (authenticity?.label) {
    rows.push({
      label: 'Local authenticity',
      value: `${authenticity.label}${typeof authenticity.score === 'number' ? ` (${Math.round(authenticity.score * 100)}%)` : ''}`,
    });
  }

  if (authenticity?.reasons?.length) {
    rows.push({
      label: 'Authenticity clues',
      value: authenticity.reasons.join('; '),
    });
  }

  if (typeof authenticity?.chain_risk === 'number' && authenticity.chain_risk >= 0.7) {
    rows.push({
      label: 'Generic risk',
      value: 'This looks chain-like, so Adventour pushes it down unless the area has few better options.',
    });
  }

  if (ranking.strategy === 'score_then_diversity') {
    if (ranking.party_coverage_rescue) {
      rows.push({
        label: 'Friend match rescue',
        value: ranking.rescued_member
          ? `Adventour made room for this because it gives ${ranking.rescued_member} a strong match.`
          : 'Adventour made room for this because it gives the travel party a stronger match.',
      });
    } else if (ranking.local_discovery_rescue) {
      const scoreGap = typeof ranking.score_gap === 'number'
        ? ` It was only ${Math.round(ranking.score_gap * 100)} points behind the card it replaced.`
        : '';
      const authenticityGain = typeof ranking.authenticity_gain === 'number' && ranking.authenticity_gain > 0
        ? ` Local signal improved by ${Math.round(ranking.authenticity_gain * 100)} points.`
        : '';
      rows.push({
        label: 'Local discovery rescue',
        value: `Adventour made room for this because the first cards needed a stronger local-feeling pick.${scoreGap}${authenticityGain}`,
      });
    } else if ((ranking.member_coverage_bonus || 0) > 0) {
      rows.push({
        label: 'Party coverage',
        value: ranking.served_new_members?.length
          ? `Lifted because it strongly matches ${ranking.served_new_members.join(', ')}.`
          : 'Lifted because it helps balance the travel party.',
      });
    }

    if ((ranking.diversity_bonus || 0) > (ranking.diversity_penalty || 0)) {
      rows.push({
        label: 'Basket variety',
        value: 'Lifted because it adds a different kind of local experience to this recommendation batch.',
      });
    } else if ((ranking.diversity_penalty || 0) > 0) {
      rows.push({
        label: 'Basket variety',
        value: 'Slightly lowered because similar picks were already in this batch.',
      });
    } else {
      rows.push({
        label: 'Basket variety',
        value: 'Kept in score order while Adventour balanced the rest of the basket.',
      });
    }
  }

  if (place.diversity_groups?.length) {
    rows.push({
      label: 'Experience mix',
      value: place.diversity_groups.map((group) => group.replace(/_/g, ' ')).join(', '),
    });
  }

  return rows;
};

const scoutStyleLabel = (place: Place) => {
  const profile = place.scoring_profile
    || place.score_components?.scoring_profile
    || place.ranking?.scoring_profile;
  const labels: Record<string, string> = {
    phase1_balanced: 'Balanced scout',
    authenticity_forward: 'Hidden gems scout',
    group_friendly: 'Group fit scout',
    fresh_discovery: 'Fresh finds scout',
    event_anchor: 'Event anchor scout',
    learned_beta: 'Learned beta',
  };
  return profile ? labels[profile] || profile.replace(/_/g, ' ') : null;
};

const objectiveBreakdownForPlace = (place: Place) => {
  const breakdown = place.ranking?.objective_breakdown;
  if (!breakdown?.positive?.length) {
    return null;
  }

  const positive = breakdown.positive
    .filter((item) => item.contribution > 0)
    .sort((a, b) => b.contribution - a.contribution);
  const maxContribution = Math.max(...positive.map((item) => item.contribution), 0.01);
  return {
    ...breakdown,
    positive,
    maxContribution,
    penalties: breakdown.penalties || [],
  };
};

const PlaceDetailsModal: React.FC<Props> = ({ place, visible, onClose }) => {
  if (!place) {
    return null;
  }

  const signals = recommendationSignals(place);
  const scoutLabel = scoutStyleLabel(place);
  const objectiveBreakdown = objectiveBreakdownForPlace(place);

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
              {scoutLabel ? <Text style={[styles.pill, styles.scoutPill]}>{scoutLabel}</Text> : null}
            </View>

            {place.explanation ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Why this showed up</Text>
                <Text style={styles.bodyText}>{place.explanation}</Text>
              </View>
            ) : null}

            {place.explanation_details?.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Why Adventour likes it</Text>
                {place.explanation_details.map((detail, index) => (
                  <View key={`${detail.kind}-${detail.label}-${index}`} style={styles.detailCard}>
                    <View style={styles.detailHeader}>
                      <Text style={styles.detailLabel}>{detail.label}</Text>
                      {typeof detail.strength === 'number' ? (
                        <Text style={styles.detailStrength}>{Math.round(detail.strength * 100)}%</Text>
                      ) : null}
                    </View>
                    <Text style={styles.detailValue}>{detail.value}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {objectiveBreakdown ? (
              <View style={styles.section}>
                <View style={styles.objectiveHeader}>
                  <View>
                    <Text style={styles.sectionTitle}>Model balance</Text>
                    <Text style={styles.objectiveSubtitle}>Weighted Adventour ranking objectives</Text>
                  </View>
                  {typeof objectiveBreakdown.final_score === 'number' ? (
                    <Text style={styles.objectiveScore}>
                      {Math.round(objectiveBreakdown.final_score * 100)}%
                    </Text>
                  ) : null}
                </View>
                {objectiveBreakdown.positive.slice(0, 6).map((objective) => {
                  const width: DimensionValue = `${Math.max(8, Math.round((objective.contribution / objectiveBreakdown.maxContribution) * 100))}%`;
                  return (
                    <View key={objective.id} style={styles.objectiveRow}>
                      <View style={styles.objectiveRowHeader}>
                        <Text style={styles.objectiveLabel}>{objective.label}</Text>
                        <Text style={styles.objectiveValue}>
                          {Math.round(objective.contribution * 100)} pts
                        </Text>
                      </View>
                      <View style={styles.objectiveTrack}>
                        <View style={[styles.objectiveFill, { width }]} />
                      </View>
                      <Text style={styles.objectiveMeta}>
                        component {Math.round(objective.component * 100)}% x weight {Math.round(objective.weight * 100)}%
                      </Text>
                    </View>
                  );
                })}
                {objectiveBreakdown.penalties.length ? (
                  <View style={styles.objectivePenaltyBox}>
                    <Text style={styles.objectivePenaltyTitle}>Score brakes</Text>
                    <View style={styles.objectivePenaltyRow}>
                      {objectiveBreakdown.penalties.slice(0, 4).map((penalty) => (
                        <Text key={penalty.id} style={styles.objectivePenaltyPill}>
                          {penalty.label} -{Math.round(penalty.penalty * 100)}
                        </Text>
                      ))}
                    </View>
                  </View>
                ) : null}
              </View>
            ) : null}

            {signals.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Recommendation signals</Text>
                {signals.map((signal) => (
                  <View key={signal.label} style={styles.signalRow}>
                    <Text style={styles.signalLabel}>{signal.label}</Text>
                    <Text style={styles.signalValue}>{signal.value}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            {place.member_fit?.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Travel party fit</Text>
                {place.member_fit.map((member) => (
                  <View key={member.user_id} style={styles.fitRow}>
                    <Text style={styles.fitName}>{member.display_name}</Text>
                    <Text style={styles.fitScore}>{Math.round(member.fit * 100)}%</Text>
                  </View>
                ))}
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
  scoutPill: {
    backgroundColor: '#e8f8fb',
    color: '#123c69',
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
  detailCard: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 7,
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  detailHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  detailLabel: {
    color: '#123c69',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  detailStrength: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  detailValue: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 4,
  },
  objectiveHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  objectiveSubtitle: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    marginTop: -2,
  },
  objectiveScore: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#fffdf8',
    flexShrink: 0,
    fontSize: 12,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  objectiveRow: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 7,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  objectiveRowHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  objectiveLabel: {
    color: '#123c69',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  objectiveValue: {
    color: '#e6534b',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
  },
  objectiveTrack: {
    backgroundColor: '#cdeff6',
    borderRadius: 999,
    height: 7,
    marginTop: 7,
    overflow: 'hidden',
  },
  objectiveFill: {
    backgroundColor: '#ff9f1c',
    borderRadius: 999,
    height: 7,
  },
  objectiveMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    marginTop: 5,
  },
  objectivePenaltyBox: {
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 2,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  objectivePenaltyTitle: {
    color: '#7b4d1b',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  objectivePenaltyRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  objectivePenaltyPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#ffcf7a',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  signalRow: {
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 7,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  signalLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 2,
  },
  signalValue: {
    color: '#4b5563',
    fontSize: 12,
    lineHeight: 17,
  },
  fitRow: {
    alignItems: 'center',
    backgroundColor: '#eef8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 7,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  fitName: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '800',
  },
  fitScore: {
    color: '#e6534b',
    fontSize: 13,
    fontWeight: '900',
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
