import React, { useState } from 'react';
import { View, TextInput, TouchableOpacity, StyleSheet, Text, Alert, Image } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface Props {
  onLogin: () => void;
}

const logo = require('../src/assets/brand/adventour-logo.png');

const LoginScreen: React.FC<Props> = ({ onLogin }) => {
  const [username, setUsername] = useState('');

  const handleLogin = async () => {
    if (!username.trim()) {
      Alert.alert("Enter a username to continue");
      return;
    }
    await AsyncStorage.setItem('user_id', username.trim());
    onLogin();
  };

  return (
    <View style={styles.container}>
      <Image source={logo} style={styles.logo} resizeMode="contain" />
      <Text style={styles.title}>Pack light. Pick boldly.</Text>
      <Text style={styles.label}>Enter your username:</Text>
      <TextInput
        style={styles.input}
        value={username}
        onChangeText={setUsername}
        placeholder="Username"
      />
      <TouchableOpacity style={styles.button} onPress={handleLogin}>
        <Text style={styles.buttonText}>Continue</Text>
      </TouchableOpacity>
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    padding: 20,
    backgroundColor: '#dff6f2',
  },
  logo: {
    alignSelf: 'center',
    width: 230,
    height: 145,
    marginBottom: 8,
  },
  title: {
    color: '#123c69',
    fontSize: 24,
    fontWeight: '900',
    textAlign: 'center',
    marginBottom: 24,
  },
  label: {
    fontSize: 16,
    marginBottom: 10,
    color: '#31506b',
    fontWeight: '800',
  },
  input: {
    borderWidth: 1,
    borderColor: '#b6e2da',
    backgroundColor: '#fff',
    padding: 13,
    borderRadius: 8,
    marginBottom: 18,
  },
  button: {
    backgroundColor: '#123c69',
    borderRadius: 8,
    paddingVertical: 14,
    alignItems: 'center',
  },
  buttonText: {
    color: '#fff',
    fontWeight: '900',
    fontSize: 16,
  },
});

export default LoginScreen;
