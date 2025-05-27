import React, { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import LoginScreen from './LoginScreen';
import OnboardingScreen from './OnboardingScreen';
import HomeScreen from '../HomeScreen';
import axios from 'axios';
import Config from '../src/Config';

const Stack = createStackNavigator();

const AppNavigator = () => {
  const [userId, setUserId] = useState<string | null>(null);
  const [onboarded, setOnboarded] = useState<boolean>(false);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const loadUser = async () => {
      const id = await AsyncStorage.getItem('user_id');
      if (!id) {
        setUserId(null);
        setLoading(false);
        return;
      }

      setUserId(id);

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

  return (
    <NavigationContainer>
      <Stack.Navigator screenOptions={{ headerShown: false }}>
        {!userId ? (
          <Stack.Screen name="Login">
            {props => <LoginScreen {...props} onLogin={() => setUserId('dummy')} />}
          </Stack.Screen>
        ) : !onboarded ? (
          <Stack.Screen name="Onboarding">
            {props => <OnboardingScreen {...props} onComplete={() => setOnboarded(true)} />}
          </Stack.Screen>
        ) : (
          <Stack.Screen name="Home" component={HomeScreen} />
        )}
      </Stack.Navigator>
    </NavigationContainer>
  );
};

export default AppNavigator;
