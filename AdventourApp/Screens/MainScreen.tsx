import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

const MainScreen: React.FC = () => {
  return (
    <View style={styles.container}>
      <Text style={styles.text}>Welcome to the Main App Screen!</Text>
    </View>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  text: { fontSize: 24 },
});

export default MainScreen;
