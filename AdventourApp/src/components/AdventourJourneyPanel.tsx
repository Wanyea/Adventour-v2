import React, { useEffect, useMemo, useState } from 'react';
import {
  Image,
  Linking,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import Config from '../Config';
import { AdventourSession, AdventourStop } from '../types/Adventour';

type Props = {
  adventour: AdventourSession | null;
  loading?: boolean;
  onStart: () => void;
  onOpenDirections: (stop: AdventourStop) => void;
  onArrive: (stop: AdventourStop) => void;
  onRateStop: (stop: AdventourStop, rating: number) => void;
  onSwapStop?: (stop: AdventourStop, alternativeIndex: number) => void;
  onEnd: () => void;
};

const formatDuration = (seconds?: number) => {
  const totalSeconds = Math.max(0, seconds || 0);
  if (totalSeconds < 60) {
    return `${totalSeconds}s`;
  }

  const minutes = Math.floor(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours > 0) {
    return `${hours}h ${remainingMinutes}m`;
  }
  return `${minutes}m`;
};

const formatCurrency = (amount: number, currency?: string) => {
  const code = currency && currency !== 'mixed' ? currency : 'USD';
  return `${code} $${amount.toFixed(2)}`;
};

const formatReservationTypes = (typeCounts?: Record<string, number>) => {
  const entries = Object.entries(typeCounts || {});
  if (!entries.length) {
    return 'No saved booking types yet';
  }

  return entries
    .map(([type, count]) => `${count} ${type.replace(/_/g, ' ')}`)
    .join(' · ');
};

const formatReservationType = (type?: string) => (
  type ? type.replace(/_/g, ' ') : 'booking'
);

const reservationProviderLine = (provider?: string, startsAt?: string) => {
  const parts = [provider, startsAt ? new Date(startsAt).toLocaleDateString() : undefined]
    .filter(Boolean);
  return parts.length ? parts.join(' - ') : 'Details saved for this Adventour';
};

const useElapsedSeconds = (start?: string) => {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (!start) {
      return;
    }

    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [start]);

  if (!start) {
    return 0;
  }

  const timestamp = /(?:Z|[+-]\d{2}:?\d{2})$/.test(start) ? start : `${start}Z`;
  return Math.max(0, Math.floor((now - new Date(timestamp).getTime()) / 1000));
};

const photoUrlForStop = (stop: AdventourStop) => {
  const url = stop.display?.photo_url;
  if (!url) {
    return undefined;
  }
  return url.startsWith('http') ? url : `${Config.BACKEND_BASE_URL}${url}`;
};

const alternativeName = (alternative: Record<string, any>) => (
  alternative?.name || alternative?.display?.name || 'Swap option'
);

const alternativeSwapLine = (alternative: Record<string, any>) => {
  const decision = alternative?.swap_impact?.swap_decision;
  if (decision?.headline) {
    return decision.headline;
  }
  const delta = alternative?.swap_impact?.route_score_delta;
  if (typeof delta === 'number') {
    const sign = delta > 0 ? '+' : '';
    return `${sign}${Math.round(delta * 100)}% route fit`;
  }
  const label = alternative?.authenticity_evidence?.label;
  return label ? `${label} alternative` : 'Keep the route, change the vibe';
};

const AdventourJourneyPanel: React.FC<Props> = ({
  adventour,
  loading,
  onStart,
  onOpenDirections,
  onArrive,
  onRateStop,
  onSwapStop,
  onEnd,
}) => {
  const [tripLogOpen, setTripLogOpen] = useState(false);
  const [bookingDetailsOpen, setBookingDetailsOpen] = useState(false);
  const activeStop = adventour?.active_stop || null;
  const activeStopAlternativeSource = activeStop?.metadata?.alternatives;
  const activeStopAlternatives = (
    Array.isArray(activeStopAlternativeSource)
      ? activeStopAlternativeSource
      : []
  ) as Record<string, any>[];
  const elapsedAtStop = useElapsedSeconds(activeStop?.arrived_at);
  const completedStops = adventour?.stops.filter((stop) => stop.status === 'completed') || [];
  const visitedStops = adventour?.stops.filter((stop) => (
    stop.status === 'completed' || stop.status === 'arrived'
  )) || [];
  const bookingSummary = adventour?.booking_summary;
  const reservations = adventour?.reservations || [];
  const hasSavedBookings = Boolean(bookingSummary?.reservation_count);
  const currentPhotoUrl = activeStop ? photoUrlForStop(activeStop) : undefined;
  const statusLabel = useMemo(() => {
    if (!adventour) {
      return 'Ready when you are';
    }
    if (!activeStop) {
      return 'Pick your next place';
    }
    if (activeStop.status === 'arrived') {
      return `Here for ${formatDuration(elapsedAtStop)}`;
    }
    return 'Directions ready';
  }, [activeStop, adventour, elapsedAtStop]);

  if (!adventour) {
    return (
      <View style={[styles.panel, styles.idlePanel]}>
        <View style={styles.headerRow}>
          <View style={styles.headerText}>
            <Text style={styles.kicker}>Trip mode</Text>
            <Text style={styles.title}>Save accepted places into an Adventour</Text>
          </View>
          <TouchableOpacity style={styles.startButton} onPress={onStart} disabled={loading}>
            <Text style={styles.startButtonText}>{loading ? 'Starting' : 'Start'}</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.panel}>
      <View style={styles.headerRow}>
        <View style={styles.headerText}>
          <Text style={styles.kicker}>Active Adventour</Text>
          <Text style={styles.title}>{statusLabel}</Text>
        </View>
        <TouchableOpacity style={styles.endButton} onPress={onEnd} disabled={loading}>
          <Text style={styles.endButtonText}>End</Text>
        </TouchableOpacity>
      </View>

      {activeStop ? (
        <View style={styles.stopCard}>
          {currentPhotoUrl ? (
            <Image source={{ uri: currentPhotoUrl }} style={styles.stopImage} />
          ) : (
            <View style={styles.stopImageFallback}>
              <Text style={styles.stopImageFallbackText}>AD</Text>
            </View>
          )}
          <View style={styles.stopContent}>
            <Text style={styles.stopName} numberOfLines={1}>
              {activeStop.display?.name || 'Current stop'}
            </Text>
            <Text style={styles.stopAddress} numberOfLines={1}>
              {activeStop.display?.vicinity || 'Open directions when you are ready.'}
            </Text>
            {activeStop.status === 'planned' && activeStopAlternatives.length && onSwapStop ? (
              <View style={styles.swapRail}>
                <Text style={styles.swapRailLabel}>Swap ideas</Text>
                {activeStopAlternatives.slice(0, 2).map((alternative, index) => (
                  <TouchableOpacity
                    key={`${alternative.provider_place_id || alternative.place_id || alternativeName(alternative)}-${index}`}
                    style={styles.swapIdeaButton}
                    onPress={() => onSwapStop(activeStop, index)}
                    disabled={loading}
                    activeOpacity={0.84}
                  >
                    <Text style={styles.swapIdeaName} numberOfLines={1}>
                      {alternativeName(alternative)}
                    </Text>
                    <Text style={styles.swapIdeaMeta} numberOfLines={1}>
                      {alternativeSwapLine(alternative)}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.secondaryButton} onPress={() => onOpenDirections(activeStop)}>
                <Text style={styles.secondaryButtonText}>Directions</Text>
              </TouchableOpacity>
              {activeStop.status !== 'arrived' ? (
                <TouchableOpacity style={styles.primaryButton} onPress={() => onArrive(activeStop)}>
                  <Text style={styles.primaryButtonText}>I'm here</Text>
                </TouchableOpacity>
              ) : (
                <View style={styles.ratingRow}>
                  {[1, 2, 3, 4, 5].map((rating) => (
                    <TouchableOpacity
                      key={rating}
                      style={styles.ratingButton}
                      onPress={() => onRateStop(activeStop, rating)}
                    >
                      <Text style={styles.ratingText}>{rating}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </View>
          </View>
        </View>
      ) : (
        <Text style={styles.helper}>
          Your Adventour is live. Swipe right on a recommendation to make it the next stop.
        </Text>
      )}

      <View style={styles.progressRow}>
        <Text style={styles.progressText}>{completedStops.length} stop{completedStops.length === 1 ? '' : 's'} finished</Text>
        <Text style={styles.progressText}>{adventour.stops.length} total picked</Text>
      </View>

      {hasSavedBookings && bookingSummary ? (
        <View style={styles.bookingSummaryCard}>
          <View style={styles.bookingSummaryHeader}>
            <View>
              <Text style={styles.bookingSummaryKicker}>Trip bookings</Text>
              <Text style={styles.bookingSummaryTitle}>
                {bookingSummary.reservation_count} saved · {Math.round(bookingSummary.readiness_score * 100)}% ready
              </Text>
            </View>
            <Text style={styles.bookingSummaryCost}>
              {formatCurrency(bookingSummary.known_cost_per_person, bookingSummary.currency)} / person
            </Text>
          </View>
          <Text style={styles.bookingSummaryTypes} numberOfLines={1}>
            {formatReservationTypes(bookingSummary.type_counts)}
          </Text>
          <Text style={styles.bookingSummaryMessage} numberOfLines={2}>
            {bookingSummary.message}
          </Text>
          <View style={styles.bookingMetaRow}>
            <Text style={styles.bookingMetaPill}>
              {bookingSummary.confirmation_count} confirmed
            </Text>
            <Text style={styles.bookingMetaPill}>
              {bookingSummary.booking_link_count} links
            </Text>
            <TouchableOpacity onPress={() => setBookingDetailsOpen((current) => !current)}>
              <Text style={styles.bookingDetailsToggle}>{bookingDetailsOpen ? 'Hide details' : 'View details'}</Text>
            </TouchableOpacity>
          </View>
          {bookingDetailsOpen && reservations.length > 0 ? (
            <View style={styles.reservationList}>
              {reservations.slice(0, 4).map((reservation) => (
                <View key={reservation.id} style={styles.reservationItem}>
                  <View style={styles.reservationHeader}>
                    <Text style={styles.reservationType}>
                      {formatReservationType(reservation.reservation_type)}
                    </Text>
                    {reservation.booking_url ? (
                      <TouchableOpacity
                        style={styles.reservationLinkButton}
                        onPress={() => Linking.openURL(reservation.booking_url as string)}
                      >
                        <Text style={styles.reservationLinkText}>Open</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  <Text style={styles.reservationTitle} numberOfLines={1}>
                    {reservation.title}
                  </Text>
                  <Text style={styles.reservationProvider} numberOfLines={1}>
                    {reservationProviderLine(reservation.provider, reservation.starts_at)}
                  </Text>
                  {reservation.confirmation_code ? (
                    <Text style={styles.confirmationCode} numberOfLines={1}>
                      Confirmation {reservation.confirmation_code}
                    </Text>
                  ) : null}
                  {typeof reservation.cost_total === 'number' ? (
                    <Text style={styles.reservationCost}>
                      {formatCurrency(reservation.cost_total, reservation.currency)}
                    </Text>
                  ) : null}
                </View>
              ))}
              {reservations.length > 4 ? (
                <Text style={styles.moreReservationsText}>
                  +{reservations.length - 4} more saved booking{reservations.length - 4 === 1 ? '' : 's'}
                </Text>
              ) : null}
            </View>
          ) : null}
        </View>
      ) : null}

      {visitedStops.length > 0 && (
        <View style={styles.tripLog}>
          <TouchableOpacity
            style={styles.tripLogHeader}
            onPress={() => setTripLogOpen((current) => !current)}
          >
            <View>
              <Text style={styles.tripLogKicker}>Trip log</Text>
              <Text style={styles.tripLogTitle}>
                {visitedStops.length} place{visitedStops.length === 1 ? '' : 's'} visited so far
              </Text>
            </View>
            <Text style={styles.tripLogToggle}>{tripLogOpen ? 'Hide' : 'View'}</Text>
          </TouchableOpacity>

          {tripLogOpen && (
            <View style={styles.tripLogList}>
              {visitedStops.map((stop, index) => {
                const isCurrentStop = activeStop?.id === stop.id;
                const duration = isCurrentStop ? elapsedAtStop : stop.duration_seconds;

                return (
                  <View key={stop.id} style={styles.tripLogItem}>
                    <View style={styles.tripLogIndex}>
                      <Text style={styles.tripLogIndexText}>{index + 1}</Text>
                    </View>
                    <View style={styles.tripLogContent}>
                      <View style={styles.tripLogNameRow}>
                        <Text style={styles.tripLogName} numberOfLines={1}>
                          {stop.display?.name || 'Adventour stop'}
                        </Text>
                        {isCurrentStop && (
                          <Text style={styles.currentBadge}>Here now</Text>
                        )}
                      </View>
                      <Text style={styles.tripLogMeta} numberOfLines={1}>
                        {stop.display?.vicinity || 'Saved Adventour stop'} - {formatDuration(duration)}
                      </Text>
                      {stop.status === 'completed' && (
                        <View style={styles.historyRatingRow}>
                          {[1, 2, 3, 4, 5].map((rating) => (
                            <TouchableOpacity
                              key={rating}
                              style={[
                                styles.historyRatingButton,
                                stop.rating === rating && styles.historyRatingButtonActive,
                              ]}
                              onPress={() => onRateStop(stop, rating)}
                            >
                              <Text
                                style={[
                                  styles.historyRatingText,
                                  stop.rating === rating && styles.historyRatingTextActive,
                                ]}
                              >
                                {rating}
                              </Text>
                            </TouchableOpacity>
                          ))}
                        </View>
                      )}
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  panel: {
    backgroundColor: '#123c69',
    borderRadius: 8,
    padding: 12,
    marginBottom: 10,
    shadowColor: '#0f172a',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.14,
    shadowRadius: 8,
    elevation: 4,
  },
  idlePanel: {
    paddingVertical: 10,
  },
  headerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  headerText: {
    flex: 1,
    paddingRight: 10,
  },
  kicker: {
    color: '#ff9f1c',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
    letterSpacing: 0.6,
  },
  title: {
    color: '#fffaf3',
    fontSize: 16,
    fontWeight: '900',
    marginTop: 2,
  },
  helper: {
    color: '#dff6f2',
    fontSize: 12,
    lineHeight: 17,
    marginTop: 8,
  },
  startButton: {
    backgroundColor: '#ff9f1c',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingVertical: 9,
  },
  startButtonText: {
    color: '#111827',
    fontWeight: '900',
  },
  endButton: {
    borderColor: '#ff9f1c',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 13,
    paddingVertical: 7,
  },
  endButtonText: {
    color: '#fffaf3',
    fontWeight: '900',
  },
  stopCard: {
    marginTop: 10,
    backgroundColor: '#fffaf3',
    borderRadius: 8,
    overflow: 'hidden',
    flexDirection: 'row',
  },
  stopImage: {
    width: 86,
    minHeight: 96,
    backgroundColor: '#e5e7eb',
  },
  stopImageFallback: {
    width: 86,
    minHeight: 96,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fed7aa',
  },
  stopImageFallbackText: {
    color: '#9a3412',
    fontWeight: '900',
  },
  stopContent: {
    flex: 1,
    padding: 10,
  },
  stopName: {
    color: '#111827',
    fontSize: 15,
    fontWeight: '900',
  },
  stopAddress: {
    color: '#6b7280',
    fontSize: 12,
    marginTop: 3,
  },
  swapRail: {
    backgroundColor: '#dff6f2',
    borderColor: '#9ad8e8',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 8,
  },
  swapRailLabel: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.5,
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  swapIdeaButton: {
    backgroundColor: '#fffaf3',
    borderColor: '#f3d8b5',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 5,
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  swapIdeaName: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  swapIdeaMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    marginTop: 2,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 10,
  },
  secondaryButton: {
    borderColor: '#123c69',
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 8,
    marginRight: 8,
  },
  secondaryButtonText: {
    color: '#123c69',
    fontWeight: '900',
    fontSize: 12,
  },
  primaryButton: {
    backgroundColor: '#e6534b',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  primaryButtonText: {
    color: '#fff',
    fontWeight: '900',
    fontSize: 12,
  },
  ratingRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
  },
  ratingButton: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#ff9f1c',
    marginRight: 5,
  },
  ratingText: {
    color: '#111827',
    fontWeight: '900',
    fontSize: 12,
  },
  progressRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 9,
  },
  progressText: {
    color: '#dff6f2',
    fontSize: 11,
    fontWeight: '800',
  },
  bookingSummaryCard: {
    backgroundColor: '#dff6f2',
    borderColor: '#9ad8e8',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 10,
  },
  bookingSummaryHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  bookingSummaryKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  bookingSummaryTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  bookingSummaryCost: {
    color: '#123c69',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    marginTop: 2,
    textAlign: 'right',
  },
  bookingSummaryTypes: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 7,
    textTransform: 'capitalize',
  },
  bookingSummaryMessage: {
    color: '#31506b',
    fontSize: 11,
    lineHeight: 15,
    marginTop: 4,
  },
  bookingMetaRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  bookingMetaPill: {
    backgroundColor: '#fffaf3',
    borderColor: '#9ad8e8',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  bookingDetailsToggle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginLeft: 2,
    textDecorationLine: 'underline',
  },
  reservationList: {
    borderTopColor: '#9ad8e8',
    borderTopWidth: 1,
    marginTop: 9,
    paddingTop: 8,
  },
  reservationItem: {
    backgroundColor: '#fffaf3',
    borderColor: '#f3d8b5',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    padding: 9,
  },
  reservationHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  reservationType: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  reservationLinkButton: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 4,
  },
  reservationLinkText: {
    color: '#fffaf3',
    fontSize: 10,
    fontWeight: '900',
  },
  reservationTitle: {
    color: '#111827',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 5,
  },
  reservationProvider: {
    color: '#6b7280',
    fontSize: 11,
    marginTop: 2,
  },
  confirmationCode: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 5,
  },
  reservationCost: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 3,
  },
  moreReservationsText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 8,
    textAlign: 'center',
  },
  tripLog: {
    backgroundColor: '#fffaf3',
    borderRadius: 8,
    marginTop: 10,
    overflow: 'hidden',
  },
  tripLogHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    padding: 10,
  },
  tripLogKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
    textTransform: 'uppercase',
  },
  tripLogTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  tripLogToggle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  tripLogList: {
    borderTopColor: '#f3d8b5',
    borderTopWidth: 1,
    padding: 10,
    paddingTop: 4,
  },
  tripLogItem: {
    flexDirection: 'row',
    paddingTop: 9,
  },
  tripLogIndex: {
    alignItems: 'center',
    backgroundColor: '#ff9f1c',
    borderRadius: 12,
    height: 24,
    justifyContent: 'center',
    marginRight: 9,
    width: 24,
  },
  tripLogIndexText: {
    color: '#111827',
    fontSize: 11,
    fontWeight: '900',
  },
  tripLogContent: {
    flex: 1,
    paddingBottom: 8,
  },
  tripLogNameRow: {
    alignItems: 'center',
    flexDirection: 'row',
  },
  tripLogName: {
    color: '#111827',
    flex: 1,
    fontSize: 13,
    fontWeight: '900',
  },
  currentBadge: {
    backgroundColor: '#dff6f2',
    borderRadius: 999,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    marginLeft: 8,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripLogMeta: {
    color: '#6b7280',
    fontSize: 11,
    marginTop: 2,
  },
  historyRatingRow: {
    flexDirection: 'row',
    marginTop: 7,
  },
  historyRatingButton: {
    alignItems: 'center',
    borderColor: '#ff9f1c',
    borderRadius: 12,
    borderWidth: 1,
    height: 24,
    justifyContent: 'center',
    marginRight: 5,
    width: 24,
  },
  historyRatingButtonActive: {
    backgroundColor: '#ff9f1c',
  },
  historyRatingText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  historyRatingTextActive: {
    color: '#111827',
  },
});

export default AdventourJourneyPanel;
