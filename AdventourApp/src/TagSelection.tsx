import React, { useState } from 'react';
import { View, Button, StyleSheet } from 'react-native';

type TagSelectionProps = {
  onSubmit: (selectedTags: string[]) => void;
};

type Tag = {
  label: string;
  value: string;
};

const tags: Tag[] = [
  { label: 'Restaurants', value: 'restaurant' },
  { label: 'Museums', value: 'museum' },
  { label: 'Parks', value: 'park' },
  { label: 'Cafes', value: 'cafe' },
  { label: 'Shopping Malls', value: 'shopping_mall' },
];

const TagSelection: React.FC<TagSelectionProps> = ({ onSubmit }) => {
  const [selectedTags, setSelectedTags] = useState<string[]>([]);

  const toggleTag = (value: string) => {
    setSelectedTags((prev: string[]) =>
      prev.includes(value)
        ? prev.filter((tag) => tag !== value)
        : [...prev, value]
    );
  };

  return (
    <View style={styles.container}>
      {tags.map((tag) => (
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
  },
});

export default TagSelection;
