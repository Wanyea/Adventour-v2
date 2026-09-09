import axios from 'axios';
import Config from '../Config';
import { Place } from '../types/Place';
import { tagGroupIdsForPlace } from '../placeTagGroups';

export type Coordinates = { latitude: number; longitude: number };
export type LocationMode = 'none' | 'gps' | 'home' | 'manual';
export type RequestStep = 'geocode' | 'recommendations';
export type RadiusOption = {
  id: 'walkable' | 'nearby' | 'explore' | 'wide';
  label: string;
  helper: string;
  meters: number;
};

export const RADIUS_OPTIONS: RadiusOption[] = [
  { id: 'walkable', label: 'Walkable', helper: '10 min', meters: 800 },
  { id: 'nearby', label: 'Nearby', helper: '2 mi', meters: 3200 },
  { id: 'explore', label: 'Explore', helper: '5 mi', meters: 8000 },
  { id: 'wide', label: 'Wide', helper: '10 mi', meters: 16000 },
];

export const describeAxiosError = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    return {
      message: error.message,
      code: error.code,
      status: error.response?.status,
      data: error.response?.data,
      url: error.config?.url,
      method: error.config?.method,
    };
  }
  return error;
};

export const placeFromRecommendation = (item: any): Place => {
  const name = item.name || item.display?.name || 'Unknown place';
  const types = item.display?.types || [];
  const place = {
    place_id: String(item.place_id || item.provider_place_id),
    provider: item.provider,
    provider_place_id: item.provider_place_id,
    decision_id: item.decision_id,
    pilot_decision_id: item.pilot_decision_id,
    model: item.model,
    structural_score: item.structural_score,
    ranking_components: item.ranking_components,
    matched_interests: item.matched_interests,
    feedback_count: item.feedback_count,
    score_components: item.score_components,
    approximate_location: item.approximate_location,
    needs_booking: item.needs_booking,
    name,
    vicinity: item.display?.vicinity || `${item.distance_meters ?? 'Unknown'} meters away`,
    types,
    category: item.category,
    explanation: item.explanation,
    photo_url: item.display?.photo_url
      ? `${Config.BACKEND_BASE_URL}${item.display.photo_url}`
      : undefined,
    photo_attributions: item.display?.photo_attributions || [],
    rating: item.display?.rating,
    user_ratings_total: item.display?.user_ratings_total,
    price_level: item.display?.price_level,
    relevance: item.score,
    likelihood: item.score,
    latitude: item.latitude,
    longitude: item.longitude,
    distance_meters: item.distance_meters,
    travel_times: item.travel_times,
  };

  return {
    ...place,
    tag_groups: item.tag_groups || tagGroupIdsForPlace(place),
  };
};
