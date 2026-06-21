export type Place = {
  place_id: string;
  provider?: string;
  provider_place_id?: string;
  name: string;
  vicinity: string;
  types: string[];
  category?: 'food' | 'activity';
  tag_groups?: string[];
  explanation?: string;
  photo_url?: string;
  photo_attributions?: any[];
  rating?: number;
  relevance?: number;
  user_ratings_total?: number;
  price_level?: number;
  photos?: any[]; 
  likelihood?: number;
  latitude?: number;
  longitude?: number;
  distance_meters?: number;
  travel_times?: {
    walk_minutes?: number;
    drive_minutes?: number;
    transit_minutes?: number;
  };
};
