import React from 'react';
import { View, Text, FlatList, Button, StyleSheet } from 'react-native';

type Place = {
  place_id: string;
  name: string;
  vicinity: string;
  rating?: number;
  types: string[];
};

type Props = {
  places: Place[];
  onFeedback: (place: Place, feedback: string) => void;
};

const PlaceList: React.FC<Props> = ({ places, onFeedback }) => {
  return (
    <FlatList
      data={places}
      keyExtractor={(item) => item.place_id}
      renderItem={({ item }) => (
        <View style={styles.item}>
          <Text style={styles.name}>{item.name}</Text>
          <Text style={styles.vicinity}>{item.vicinity}</Text>
          <Text style={styles.rating}>
            Rating: {item.rating ? `${item.rating} / 5` : 'N/A'}
          </Text>
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
  rating: {
    fontSize: 14,
    color: '#888',
    marginTop: 5,
  },
  buttonContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
});

export default PlaceList;
