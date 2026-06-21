import React, { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Image } from 'react-native';
import LoginScreen from './LoginScreen';
import FirebaseAuthScreen from './FirebaseAuthScreen';
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

const AppNavigator = () => {
  const [user, setUser] = useState<User | null>(null);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);
  const [useLegacyAuth, setUseLegacyAuth] = useState<boolean>(false);

  useEffect(() => {
    const loadUser = async () => {
      // Try Firebase auth first
      try {
        const currentUser = await AuthService.getCurrentUser();
        if (currentUser) {
          setUser(currentUser);
          
          // Check if user is onboarded
          try {
            const response = await axios.get(`${Config.BACKEND_BASE_URL}/user/${currentUser.firebase_uid}`);
            setOnboarded(response.data.onboarded);
          } catch (e) {
            console.error("Error checking onboarding:", e);
            setOnboarded(false);
          }
          
          setLoading(false);
          return;
        }
      } catch (error) {
        console.log("Firebase auth not available, falling back to legacy auth");
      }

      // Fallback to legacy auth
      const id = await AsyncStorage.getItem('user_id');
      if (!id) {
        setUser(null);
        setLoading(false);
        return;
      }

      setUseLegacyAuth(true);
      setUser({ id: 0, firebase_uid: id, email: '', username: id, display_name: id } as User);

      try {
        const response = await axios.get(`${Config.BACKEND_BASE_URL}/user/${id}`);
        setOnboarded(response.data.onboarded);
        console.log("User loaded from backend:", response.data);
      } catch (e) {
        console.error("Error checking onboarding:", e);
        setOnboarded(false);
      }

      setLoading(false);
    };

    loadUser();
  }, []);

  if (loading) return null;

  const handleAuthSuccess = (authUser: User) => {
    setUser(authUser);
    setUseLegacyAuth(false);
  };

  const handleLegacyLogin = () => {
    setUseLegacyAuth(true);
    setUser({ id: 0, firebase_uid: 'dummy', email: '', username: 'dummy', display_name: 'dummy' } as User);
  };

  const MainTabs = () => (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerStyle: {
          backgroundColor: '#bfeaf4',
          shadowColor: 'transparent',
          elevation: 0,
        },
        headerTintColor: '#123c69',
        headerTitleStyle: {
          fontWeight: '900',
        },
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
        component={HomeScreen}
        options={{ title: 'Discover' }}
      />
      <Tab.Screen 
        name="Social" 
        component={SocialScreen}
        options={{ title: 'Friends & Trips' }}
      />
      <Tab.Screen
        name="Profile"
        component={ProfileScreen}
        options={{ title: 'Profile' }}
      />
    </Tab.Navigator>
  );

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!user ? (
          <Stack.Screen name="Auth">
            {props => (
              <FirebaseAuthScreen 
                {...props} 
                onAuthSuccess={handleAuthSuccess} 
              />
            )}
          </Stack.Screen>
        ) : useLegacyAuth ? (
          <Stack.Screen name="LegacyLogin">
            {props => <LoginScreen {...props} onLogin={handleLegacyLogin} />}
          </Stack.Screen>
        ) : !onboarded ? (
          <Stack.Screen name="Onboarding">
            {props => <OnboardingScreen {...props} onComplete={() => setOnboarded(true)} />}
          </Stack.Screen>
        ) : (
          <Stack.Screen name="Main" component={MainTabs} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default AppNavigator;
