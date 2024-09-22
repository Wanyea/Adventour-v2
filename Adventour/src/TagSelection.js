import React, { useState } from 'react';
import { View, Button, StyleSheet } from 'react-native';

const tags = [
  { label: "Restaurants", value: "restaurant" },
  { label: "Museums", value: "museum" },
  { label: "Parks", value: "park" },
  { label: "Cafes", value: "cafe" },
  { label: "Shopping Malls", value: "shopping_mall" }
];

const TagSelection = ({ onSubmit }) => {
  const [selectedTags, setSelectedTags] = useState([]);

  const toggleTag = (value) => {
    setSelectedTags(prev =>
      prev.includes(value)
        ? prev.filter(tag => tag !== value)
        : [...prev, value]
    );
  };

  return (
    <View style={styles.container}>
      {tags.map(tag => (
        <Button
          key={tag.value}
          title={tag.label}
          onPress={() => toggleTag(tag.value)}
          color={selectedTags.includes(tag.value) ? 'green' : 'gray'}
        />
      ))}
      <Button title="Find Places" onPress={() => onSubmit(selectedTags)} />
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    padding: 10,
    justifyContent: 'center',
  }
});

export default TagSelection;
