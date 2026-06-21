import React, { useEffect, useMemo, useState } from 'react';
import {
  Image,
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
  onEnd: () => void;
};

const formatDuration = (seconds?: number) => {
  const totalSeconds = Math.max(0, seconds || 0);
  const minutes = Math.floor(totalSeconds / 60);
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  if (hours > 0) {
    return `${hours}h ${remainingMinutes}m`;
  }
  return `${Math.max(1, minutes)}m`;
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

  return Math.max(0, Math.floor((now - new Date(start).getTime()) / 1000));
};

const photoUrlForStop = (stop: AdventourStop) => {
  const url = stop.display?.photo_url;
  if (!url) {
    return undefined;
  }
  return url.startsWith('http') ? url : `${Config.BACKEND_BASE_URL}${url}`;
};

const AdventourJourneyPanel: React.FC<Props> = ({
  adventour,
  loading,
  onStart,
  onOpenDirections,
  onArrive,
  onRateStop,
  onEnd,
}) => {
  const activeStop = adventour?.active_stop || null;
  const elapsedAtStop = useElapsedSeconds(activeStop?.arrived_at);
  const completedStops = adventour?.stops.filter((stop) => stop.status === 'completed') || [];
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
});

export default AdventourJourneyPanel;
