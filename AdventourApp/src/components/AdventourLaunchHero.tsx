import React, { useEffect, useRef } from 'react';
import {
  Animated,
  Dimensions,
  Image,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';

const logo = require('../assets/brand/adventour-wordmark.png');
const balloon = require('../assets/brand/adventour-balloon.png');
const screenWidth = Dimensions.get('window').width;

type Props = {
  locationLabel: string;
  distanceLabel: string;
  loading?: boolean;
  hasResults?: boolean;
  activeStopName?: string;
  onLaunch: () => void;
};

type CloudCruiserProps = {
  delay: number;
  duration: number;
  top?: number;
  bottom?: number;
  scale?: number;
  opacity?: number;
  variant: 'large' | 'medium' | 'small';
};

const CloudCruiser: React.FC<CloudCruiserProps> = ({
  delay,
  duration,
  top,
  bottom,
  scale = 1,
  opacity = 1,
  variant,
}) => {
  const travel = useRef(new Animated.Value(-190)).current;
  const bob = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    let stopped = false;
    const run = () => {
      travel.setValue(-210);
      Animated.sequence([
        Animated.delay(delay),
        Animated.timing(travel, {
          toValue: screenWidth + 170,
          duration,
          useNativeDriver: true,
        }),
      ]).start(({ finished }) => {
        if (finished && !stopped) {
          run();
        }
      });
    };

    run();
    return () => {
      stopped = true;
      travel.stopAnimation();
    };
  }, [delay, duration, travel]);

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(bob, {
          toValue: 1,
          duration: 2200,
          useNativeDriver: true,
        }),
        Animated.timing(bob, {
          toValue: 0,
          duration: 2200,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [bob]);

  const bobY = bob.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -5],
  });

  return (
    <Animated.View
      style={[
        styles.cloud,
        top !== undefined ? { top } : { bottom },
        {
          opacity,
          transform: [{ translateX: travel }, { translateY: bobY }, { scale }],
        },
      ]}
    >
      {variant === 'large' ? (
        <>
          <View style={styles.cloudPuffLarge} />
          <View style={styles.cloudPuffSmall} />
          <View style={styles.cloudPuffTiny} />
        </>
      ) : variant === 'medium' ? (
        <>
          <View style={styles.cloudPuffSmall} />
          <View style={styles.cloudPuffLarge} />
        </>
      ) : (
        <>
          <View style={styles.cloudPuffTiny} />
          <View style={styles.cloudPuffSmall} />
        </>
      )}
    </Animated.View>
  );
};

const AdventourLaunchHero: React.FC<Props> = ({
  locationLabel,
  distanceLabel,
  loading,
  hasResults,
  activeStopName,
  onLaunch,
}) => {
  const floatAnim = useRef(new Animated.Value(0)).current;
  const launchAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(floatAnim, {
          toValue: 1,
          duration: 1800,
          useNativeDriver: true,
        }),
        Animated.timing(floatAnim, {
          toValue: 0,
          duration: 1800,
          useNativeDriver: true,
        }),
      ]),
    );
    loop.start();
    return () => loop.stop();
  }, [floatAnim]);

  useEffect(() => {
    if (!loading && !hasResults) {
      launchAnim.setValue(0);
      return;
    }

    Animated.timing(launchAnim, {
      toValue: loading ? 0.45 : 1,
      duration: loading ? 260 : 520,
      useNativeDriver: true,
    }).start();
  }, [hasResults, launchAnim, loading]);

  const floatY = floatAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, -25],
  });

  const launchY = launchAnim.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 38],
  });

  const cloudDuration = loading ? 5600 : hasResults ? 6800 : 11800;

  return (
    <View style={styles.hero}>
      <CloudCruiser variant="large" top={42} delay={0} duration={cloudDuration} opacity={0.82} />
      <CloudCruiser variant="medium" bottom={74} delay={2600} duration={cloudDuration + 1800} scale={0.9} opacity={0.76} />
      <CloudCruiser variant="small" top={116} delay={5200} duration={cloudDuration + 900} scale={0.82} opacity={0.68} />

      <Image source={logo} style={styles.logo} resizeMode="contain" />

      <View style={styles.launchRow}>
        <View style={styles.copy}>
          <Text style={styles.stepLabel}>Set your launch point</Text>
          <Text style={styles.title}>Where should the balloon land?</Text>
          <Text style={styles.subtitle} numberOfLines={2}>
            {activeStopName
              ? `Currently adventouring at ${activeStopName}.`
              : `${locationLabel || 'Choose a location'} - ${distanceLabel}`}
          </Text>
          <TouchableOpacity style={styles.launchButton} activeOpacity={0.82} onPress={onLaunch} disabled={loading}>
            <Text style={styles.launchButtonText}>{loading ? 'Scouting...' : hasResults ? 'Refresh picks' : 'Launch balloon'}</Text>
          </TouchableOpacity>
        </View>

        <TouchableOpacity activeOpacity={0.82} onPress={onLaunch} disabled={loading} style={styles.balloonButton}>
          <Animated.View
            style={[
              styles.balloonWrap,
              {
                transform: [
                  { translateY: Animated.add(floatY, launchY) },
                  { rotate: loading ? '2deg' : '0deg' },
                ],
              },
            ]}
          >
            <Image source={balloon} style={styles.balloon} resizeMode="contain" />
          </Animated.View>
        </TouchableOpacity>
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  hero: {
    backgroundColor: '#bfeaf4',
    borderRadius: 8,
    paddingHorizontal: 16,
    paddingTop: 70,
    paddingBottom: 24,
    marginBottom: 10,
    minHeight: 250,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#87cfe1',
  },
  cloud: {
    position: 'absolute',
    flexDirection: 'row',
    alignItems: 'flex-end',
  },
  cloudPuffLarge: {
    width: 76,
    height: 30,
    borderRadius: 999,
    backgroundColor: 'rgba(255, 255, 255, 0.78)',
  },
  cloudPuffSmall: {
    width: 48,
    height: 24,
    borderRadius: 999,
    marginLeft: -18,
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
  },
  cloudPuffTiny: {
    width: 36,
    height: 18,
    borderRadius: 999,
    backgroundColor: 'rgba(255, 255, 255, 0.72)',
  },
  logo: {
    position: 'absolute',
    top: 0,
    left: -45,
    width: 268,
    height: 74,
    marginLeft: -12,
  },
  launchRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    justifyContent: 'space-between',
    minHeight: 156,
  },
  copy: {
    flex: 1,
    paddingRight: 12,
  },
  stepLabel: {
    color: '#e6534b',
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
    marginBottom: 5,
  },
  title: {
    color: '#123c69',
    fontSize: 22,
    lineHeight: 26,
    fontWeight: '900',
  },
  subtitle: {
    color: '#31506b',
    fontSize: 13,
    lineHeight: 18,
    marginTop: 5,
    fontWeight: '700',
  },
  launchButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#123c69',
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 9,
    marginTop: 13,
    borderWidth: 2,
    borderColor: '#ff9f1c',
  },
  launchButtonText: {
    color: '#fff',
    fontSize: 13,
    fontWeight: '900',
  },
  balloonButton: {
    alignSelf: 'stretch',
    justifyContent: 'center',
  },
  balloonWrap: {
    width: 116,
    height: 174,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 4,
  },
  balloon: {
    width: 106,
    height: 144,
  },
});

export default AdventourLaunchHero;
