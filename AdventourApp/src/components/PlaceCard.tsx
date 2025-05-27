import React from 'react';
import { View, Text, StyleSheet, Button, Image } from 'react-native';
import { Place } from '../types/Place';

type Props = {
  place: Place;
  onFeedback: (place: Place, verdict: 'accept' | 'reject') => void;
};

const PlaceCard: React.FC<Props> = ({ place, onFeedback }) => {
  return (
    <View style={styles.card}>
      <Text style={styles.name}>{place.name}</Text>
      <Text style={styles.vicinity}>{place.vicinity}</Text>
      {place.relevance !== undefined && (
        <Text style={styles.score}>
          Match Score: {(place.relevance * 100).toFixed(0)}%
        </Text>
      )}
      <Text style={styles.rating}>
        Rating: {place.rating ? `${place.rating} / 5` : 'N/A'}
        {place.user_ratings_total && ` (${place.user_ratings_total} reviews)`}
      </Text>
      {place.price_level && (
        <Text style={styles.price}>
          Price: {'$'.repeat(place.price_level)}
        </Text>
      )}
      <View style={styles.buttonContainer}>
        <Button title="ACCEPT" color="green" onPress={() => onFeedback(place, 'accept')} />
        <Button title="REJECT" color="red" onPress={() => onFeedback(place, 'reject')} />
      </View>
    </View>
  );
};

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#fff',
    padding: 15,
    marginVertical: 10,
    marginHorizontal: 10,
    borderRadius: 8,
    elevation: 3,
  },
  name: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  vicinity: {
    fontSize: 14,
    color: '#666',
    marginBottom: 4,
  },
  score: {
    fontSize: 14,
    color: '#007bff',
  },
  rating: {
    fontSize: 14,
    color: '#333',
  },
  price: {
    fontSize: 14,
    color: '#444',
  },
  buttonContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 10,
  },
});

export default PlaceCard;
