import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Image, StyleSheet, TouchableOpacity } from 'react-native';
import FirebaseAuthScreen from './FirebaseAuthScreen';
import ProfileSetupScreen from './ProfileSetupScreen';
import OnboardingScreen from './OnboardingScreen';
import HomeScreen from '../HomeScreen';
import SocialScreen from './SocialScreen';
import ProfileScreen from './ProfileScreen';
import AuthService, { User } from '../src/services/AuthService';
import axios from 'axios';
import Config from '../src/Config';

const Stack = createStackNavigator();
const Tab = createBottomTabNavigator();

const tabIcons = {
  Home: require('../src/assets/tabs/tab-pin.png'),
  Social: require('../src/assets/tabs/tab-beacon.png'),
  Profile: require('../src/assets/tabs/tab-user.png'),
};

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

const profileImageForUser = (authUser: User | null) => {
  const imageId = authUser?.profile_picture as keyof typeof profileImages | undefined;
  return imageId && profileImages[imageId] ? profileImages[imageId] : profileImages.wanyea;
};

const AppNavigator = () => {
  const [user, setUser] = useState<User | null>(null);
  const [profileComplete, setProfileComplete] = useState<boolean>(false);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  const checkOnboarding = async (authUser: User) => {
    const authUserProfileComplete = Boolean(authUser.profile_complete || (authUser.display_name && authUser.date_of_birth));
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/user/${authUser.firebase_uid}`);
      if (response.data.user) {
        setUser(response.data.user);
      }
      setOnboarded(response.data.onboarded);
      setProfileComplete(Boolean(response.data.profile_complete || response.data.user?.profile_complete));
    } catch (e) {
      console.error('Error checking onboarding:', e);
      setOnboarded(false);
      setProfileComplete(authUserProfileComplete);
    }
  };

  useEffect(() => {
    const unsubscribe = AuthService.onAuthStateChanged(async (authUser) => {
      if (authUser) {
        setUser(authUser);
        setProfileComplete(Boolean(authUser.profile_complete || (authUser.display_name && authUser.date_of_birth)));
        await checkOnboarding(authUser);
      } else {
        setUser(null);
        setProfileComplete(false);
        setOnboarded(false);
      }
      setLoading(false);
    });

    return unsubscribe;
  }, []);

  if (loading) {
    return null;
  }

  const handleAuthSuccess = async (authUser: User) => {
    setLoading(true);
    try {
      setUser(authUser);
      setProfileComplete(Boolean(authUser.profile_complete || (authUser.display_name && authUser.date_of_birth)));
      await checkOnboarding(authUser);
    } finally {
      setLoading(false);
    }
  };

  const handleSignOut = async () => {
    await AuthService.signOut();
    setUser(null);
    setProfileComplete(false);
    setOnboarded(false);
  };

  const handleAccountDeleted = async () => {
    setUser(null);
    setProfileComplete(false);
    setOnboarded(false);
  };

  const handleProfileSetupComplete = (updatedUser: User) => {
    setUser(updatedUser);
    setProfileComplete(Boolean(updatedUser.profile_complete || (updatedUser.display_name && updatedUser.date_of_birth)));
  };

  const MainTabs = () => {
    const HomeTab = () => <HomeScreen user={user} />;
    const ProfileTab = () => (
      <ProfileScreen
        onSignOut={handleSignOut}
        onAccountDeleted={handleAccountDeleted}
        onUserUpdated={setUser}
      />
    );

    return (
      <Tab.Navigator
        screenOptions={({ route, navigation }) => ({
          headerStyle: {
            backgroundColor: '#bfeaf4',
            shadowColor: 'transparent',
            elevation: 0,
          },
          headerTintColor: '#123c69',
          headerTitleStyle: {
            fontWeight: '900',
          },
          headerRight: () => (
            <TouchableOpacity
              style={styles.headerAvatarButton}
              onPress={() => navigation.navigate('Profile')}
              activeOpacity={0.82}
              accessibilityLabel="Open profile"
            >
              <Image source={profileImageForUser(user)} style={styles.headerAvatarImage} />
            </TouchableOpacity>
          ),
          tabBarStyle: {
            backgroundColor: '#123c69',
            borderTopColor: '#0b2a49',
          },
          tabBarActiveTintColor: '#ff9f1c',
          tabBarInactiveTintColor: '#dff6f2',
          tabBarIcon: ({ color, focused }) => (
            <Image
              source={tabIcons[route.name as keyof typeof tabIcons]}
              resizeMode="contain"
              style={{
                width: route.name === 'Social' ? 25 : 28,
                height: route.name === 'Social' ? 25 : 28,
                tintColor: focused ? '#ff4b47' : color,
              }}
            />
          ),
        })}
      >
        <Tab.Screen
          name="Home"
          component={HomeTab}
          options={{ title: 'Discover' }}
        />
        <Tab.Screen
          name="Social"
          component={SocialScreen}
          options={{ title: 'Friends & Trips' }}
        />
        <Tab.Screen
          name="Profile"
          component={ProfileTab}
          options={{
            title: 'Profile',
            tabBarButton: () => null,
            tabBarItemStyle: { display: 'none' },
          }}
        />
      </Tab.Navigator>
    );
  };

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!user ? (
          <Stack.Screen name="Auth">
            {(props) => (
              <FirebaseAuthScreen
                {...props}
                onAuthSuccess={handleAuthSuccess}
              />
            )}
          </Stack.Screen>
        ) : !profileComplete ? (
          <Stack.Screen name="ProfileSetup">
            {(props) => (
              <ProfileSetupScreen
                {...props}
                user={user}
                onComplete={handleProfileSetupComplete}
              />
            )}
          </Stack.Screen>
        ) : !onboarded ? (
          <Stack.Screen name="Onboarding">
            {(props) => <OnboardingScreen {...props} onComplete={() => setOnboarded(true)} />}
          </Stack.Screen>
        ) : (
          <Stack.Screen name="Main" component={MainTabs} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
};

const styles = StyleSheet.create({
  headerAvatarButton: {
    alignItems: 'center',
    backgroundColor: '#fffaf3',
    borderColor: '#123c69',
    borderRadius: 24,
    borderWidth: 3,
    height: 48,
    justifyContent: 'center',
    marginRight: 14,
    overflow: 'hidden',
    width: 48,
  },
  headerAvatarImage: {
    height: 46,
    width: 46,
  },
});

export default AppNavigator;
