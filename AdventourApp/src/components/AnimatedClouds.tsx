import React, { useEffect, useMemo, useRef } from 'react';
import { Animated, Easing, StyleSheet, useWindowDimensions, View } from 'react-native';

type AnimatedCloudsProps = {
  height?: number;
  speed?: 'slow' | 'medium' | 'fast';
};

type CloudTrack = {
  topRatio: number;
  width: number;
  height: number;
  opacity: number;
  delay: number;
  initialProgress: number;
};

const durations = {
  slow: 36000,
  medium: 28000,
  fast: 20000,
};

const tracks: CloudTrack[] = [
  { topRatio: 0.04, width: 92, height: 24, opacity: 0.78, delay: 0, initialProgress: 0.2 },
  { topRatio: 0.16, width: 126, height: 30, opacity: 0.64, delay: 4200, initialProgress: 0.56 },
  { topRatio: 0.28, width: 78, height: 22, opacity: 0.72, delay: 8200, initialProgress: 0.84 },
  { topRatio: 0.43, width: 112, height: 28, opacity: 0.68, delay: 1200, initialProgress: 0.72 },
  { topRatio: 0.58, width: 86, height: 24, opacity: 0.74, delay: 6200, initialProgress: 0.38 },
  { topRatio: 0.73, width: 138, height: 32, opacity: 0.56, delay: 10400, initialProgress: 0.08 },
  { topRatio: 0.88, width: 104, height: 26, opacity: 0.7, delay: 15000, initialProgress: 0.48 },
];

const AnimatedClouds: React.FC<AnimatedCloudsProps> = ({ height = 760, speed = 'slow' }) => {
  const { width: screenWidth } = useWindowDimensions();
  const drifts = useRef(tracks.map(() => new Animated.Value(0))).current;
  const travelDistance = screenWidth + 340;
  const startX = -220;

  const animatedTracks = useMemo(() => tracks.map((track) => ({
    ...track,
    top: Math.max(18, Math.round(height * track.topRatio)),
  })), [height]);

  useEffect(() => {
    let stopped = false;
    const activeAnimations: Animated.CompositeAnimation[] = [];

    const runTrack = (index: number, fromProgress: number, delay: number) => {
      if (stopped) {
        return;
      }

      const drift = drifts[index];
      drift.setValue(fromProgress);

      const remainingDistance = Math.max(0.02, 1 - fromProgress);
      const animation = Animated.sequence([
        Animated.delay(delay),
        Animated.timing(drift, {
          toValue: 1,
          duration: Math.max(1400, durations[speed] * remainingDistance),
          easing: Easing.linear,
          useNativeDriver: true,
        }),
      ]);

      activeAnimations.push(animation);
      animation.start(({ finished }) => {
        if (!finished || stopped) {
          return;
        }
        runTrack(index, 0, animatedTracks[index].delay);
      });
    };

    animatedTracks.forEach((track, index) => {
      runTrack(index, track.initialProgress, 0);
    });

    return () => {
      stopped = true;
      activeAnimations.forEach((animation) => animation.stop());
    };
  }, [animatedTracks, drifts, speed]);

  return (
    <View pointerEvents="none" style={[styles.layer, { height }]}>
      {animatedTracks.map((cloud, index) => {
        const translateX = drifts[index].interpolate({
          inputRange: [0, 1],
          outputRange: [startX, startX + travelDistance],
        });

        return (
          <Animated.View
            key={`${cloud.topRatio}-${cloud.width}`}
            style={[
              styles.cloud,
              {
                top: cloud.top,
                width: cloud.width,
                height: cloud.height,
                opacity: cloud.opacity,
                transform: [{ translateX }],
              },
            ]}
          >
            <View style={[styles.puff, styles.puffLeft]} />
            <View style={[styles.puff, styles.puffMiddle]} />
            <View style={[styles.puff, styles.puffRight]} />
            <View style={styles.cloudBase} />
          </Animated.View>
        );
      })}
    </View>
  );
};

const styles = StyleSheet.create({
  layer: {
    left: 0,
    overflow: 'hidden',
    position: 'absolute',
    right: 0,
    top: 0,
  },
  cloud: {
    position: 'absolute',
  },
  puff: {
    backgroundColor: '#fff',
    borderRadius: 999,
    position: 'absolute',
  },
  puffLeft: {
    bottom: 2,
    height: '64%',
    left: '3%',
    width: '44%',
  },
  puffMiddle: {
    bottom: 3,
    height: '92%',
    left: '28%',
    width: '47%',
  },
  puffRight: {
    bottom: 0,
    height: '62%',
    right: '4%',
    width: '42%',
  },
  cloudBase: {
    backgroundColor: '#fff',
    borderRadius: 999,
    bottom: 0,
    height: '48%',
    left: 0,
    position: 'absolute',
    right: 0,
  },
});

export default AnimatedClouds;
