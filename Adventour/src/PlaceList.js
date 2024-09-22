import React from 'react';
import { View, Text, FlatList, StyleSheet } from 'react-native';

const PlaceList = ({ places }) => {
  return (
    <FlatList
      data={places}
      keyExtractor={(item) => item.place_id}
      renderItem={({ item }) => (
        <View style={styles.item}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.vicinity}>{item.vicinity}</Text>
        </View>
      )}
    />
  );
};

const styles = StyleSheet.create({
  item: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#ccc',
  },
  name: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  vicinity: {
    fontSize: 14,
    color: '#555',
  },
});

export default PlaceList;
