import React from 'react';
import { FlatList } from 'react-native';
import { Place } from './types/Place';
import PlaceCard from './components/PlaceCard';

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
        <PlaceCard place={item} onFeedback={onFeedback} />
      )}
    />
  );
};

export default PlaceList;
