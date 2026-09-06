import { Place } from './types/Place';

export type TagGroupId =
  | 'food_drink'
  | 'coffee_sweets'
  | 'arts_culture'
  | 'outdoors'
  | 'nightlife'
  | 'entertainment'
  | 'shopping'
  | 'wellness'
  | 'local_gems';

export type TagGroup = {
  id: TagGroupId;
  label: string;
  emoji: string;
  description: string;
  color: string;
  backgroundColor: string;
  types: string[];
  nameHints?: string[];
};

export const TAG_GROUPS: TagGroup[] = [
  {
    id: 'food_drink',
    label: 'Food & Drink',
    emoji: '🍽️',
    description: 'Restaurants, bars, bakeries, and other places built around eating or drinking.',
    color: '#7c2d12',
    backgroundColor: '#ffedd5',
    types: [
      'bakery',
      'bar',
      'breakfast_restaurant',
      'brunch_restaurant',
      'fast_food_restaurant',
      'fine_dining_restaurant',
      'meal_takeaway',
      'mexican_restaurant',
      'pizza_restaurant',
      'restaurant',
      'sandwich_shop',
      'seafood_restaurant',
      'steak_house',
    ],
    nameHints: ['bbq', 'bistro', 'burger', 'deli', 'diner', 'grill', 'kitchen', 'pizza', 'restaurant', 'taco'],
  },
  {
    id: 'coffee_sweets',
    label: 'Coffee & Sweets',
    emoji: '☕',
    description: 'Cafes, coffee shops, dessert spots, ice cream, tea, and small treat stops.',
    color: '#854d0e',
    backgroundColor: '#fef3c7',
    types: ['cafe', 'coffee_shop', 'dessert_restaurant', 'ice_cream_shop', 'tea_house'],
    nameHints: ['cafe', 'coffee', 'donut', 'ice cream', 'tea'],
  },
  {
    id: 'arts_culture',
    label: 'Arts & Culture',
    emoji: '🎭',
    description: 'Museums, galleries, landmarks, libraries, theaters, and places with local history.',
    color: '#1e3a8a',
    backgroundColor: '#dbeafe',
    types: ['art_gallery', 'historical_landmark', 'library', 'museum', 'performing_arts_theater', 'tourist_attraction'],
  },
  {
    id: 'outdoors',
    label: 'Outdoors',
    emoji: '🌿',
    description: 'Parks, gardens, trails, campgrounds, zoos, aquariums, and open-air experiences.',
    color: '#14532d',
    backgroundColor: '#dcfce7',
    types: ['aquarium', 'campground', 'hiking_area', 'park', 'tourist_attraction', 'zoo'],
    nameHints: ['garden', 'trail'],
  },
  {
    id: 'nightlife',
    label: 'Nightlife',
    emoji: '🌙',
    description: 'Bars, clubs, comedy, concerts, and late-day social spots.',
    color: '#581c87',
    backgroundColor: '#f3e8ff',
    types: ['bar', 'comedy_club', 'concert_hall', 'night_club'],
  },
  {
    id: 'entertainment',
    label: 'Entertainment',
    emoji: '🎟️',
    description: 'Movies, amusement parks, performances, live events, and playful things to do.',
    color: '#9f1239',
    backgroundColor: '#ffe4e6',
    types: ['amusement_park', 'comedy_club', 'concert_hall', 'movie_theater', 'performing_arts_theater'],
  },
  {
    id: 'shopping',
    label: 'Shopping',
    emoji: '🛍️',
    description: 'Markets, bookstores, malls, boutiques, and browse-worthy local retail.',
    color: '#134e4a',
    backgroundColor: '#ccfbf1',
    types: ['book_store', 'clothing_store', 'market', 'shopping_mall'],
    nameHints: ['market', 'boutique'],
  },
  {
    id: 'wellness',
    label: 'Wellness',
    emoji: '🌸',
    description: 'Spas and slower places for relaxing, resetting, or recovering between stops.',
    color: '#365314',
    backgroundColor: '#ecfccb',
    types: ['spa'],
  },
  {
    id: 'local_gems',
    label: 'Local Gems',
    emoji: '💎',
    description: 'Locally endorsed destinations. Popular places can be local gems too.',
    color: '#92400e',
    backgroundColor: '#fef3c7',
    types: [],
  },
];

const normalize = (value: string) => value.toLowerCase().replace(/\s+/g, '_');

export const tagGroupsForPlace = (place: Pick<Place, 'name' | 'types' | 'user_ratings_total'>): TagGroup[] => {
  const types = new Set((place.types || []).map(normalize));
  const normalizedName = (place.name || '').toLowerCase();
  const groups = TAG_GROUPS.filter((group) => {
    const typeMatch = group.types.some((type) => types.has(normalize(type)));
    const nameMatch = (group.nameHints || []).some((hint) => new RegExp(`\\b${hint}\\b`, 'i').test(normalizedName));
    return typeMatch || nameMatch;
  });

  return groups;
};

export const tagGroupLabelsForPlace = (place: Pick<Place, 'name' | 'types' | 'user_ratings_total'>) =>
  tagGroupsForPlace(place).map((group) => group.label);

export const tagGroupIdsForPlace = (place: Pick<Place, 'name' | 'types' | 'user_ratings_total'>) =>
  tagGroupsForPlace(place).map((group) => group.id);

export const tagGroupLabel = (groupId: string) =>
  TAG_GROUPS.find((group) => group.id === groupId)?.label || groupId;

export const tagGroupDisplayLabel = (groupId: string) => {
  const group = TAG_GROUPS.find((item) => item.id === groupId);
  return group ? `${group.emoji} ${group.label}` : groupId;
};

export const tagGroupMeta = (groupId: string) =>
  TAG_GROUPS.find((group) => group.id === groupId);
