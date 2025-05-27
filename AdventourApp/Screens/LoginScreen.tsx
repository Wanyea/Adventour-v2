import React, { useState } from 'react';
import { View, TextInput, Button, StyleSheet, Text, Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

interface Props {
  onLogin: () => void;
}

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
      <Text style={styles.label}>Enter your username:</Text>
      <TextInput
        style={styles.input}
        value={username}
        onChangeText={setUsername}
        placeholder="Username"
      />
      <Button title="Continue" onPress={handleLogin} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, justifyContent: 'center', padding: 20 },
  label: { fontSize: 18, marginBottom: 10 },
  input: { borderWidth: 1, borderColor: '#ccc', padding: 10, marginBottom: 20 },
});

export default LoginScreen;
