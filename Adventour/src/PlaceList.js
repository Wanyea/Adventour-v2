import React from 'react';
import { View, Text, FlatList, Button, StyleSheet } from 'react-native';

const PlaceList = ({ places, onFeedback }) => {
  console.log("onFeedback prop in PlaceList:", onFeedback); // Debug log

  return (
    <FlatList
      data={places}
      keyExtractor={(item) => item.place_id}
      renderItem={({ item }) => (
        <View style={styles.item}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.vicinity}>{item.vicinity}</Text>
          <View style={styles.buttonContainer}>
            <Button
              title="Accept"
              onPress={() => onFeedback(item, 'accept')}
              color="green"
            />
            <Button
              title="Reject"
              onPress={() => onFeedback(item, 'reject')}
              color="red"
            />
          </View>
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
  buttonContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
});

export default PlaceList;
