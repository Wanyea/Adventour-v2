export type Place = {
  place_id: string;
  name: string;
  vicinity: string;
  types: string[];
  rating?: number;
  relevance?: number;
  user_ratings_total?: number;
  price_level?: number;
  photos?: any[]; 
  likelihood?: number;
};
