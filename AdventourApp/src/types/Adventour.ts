export type AdventourStopDisplay = {
  name?: string;
  vicinity?: string;
  types?: string[];
  photo_url?: string;
  photo_attributions?: any[];
  rating?: number;
  user_ratings_total?: number;
  price_level?: number;
  latitude?: number;
  longitude?: number;
};

export type AdventourStop = {
  id: number;
  session_id: number;
  place_id: string;
  decision_id?: string;
  provider?: string;
  provider_place_id?: string;
  order_index: number;
  status: 'planned' | 'navigating' | 'arrived' | 'completed' | 'skipped';
  selected_at?: string;
  navigation_started_at?: string;
  arrived_at?: string;
  departed_at?: string;
  duration_seconds?: number;
  rating?: number;
  notes?: string;
  display: AdventourStopDisplay;
};

export type AdventourSession = {
  id: number;
  title: string;
  status: 'active' | 'completed' | 'abandoned';
  started_at?: string;
  ended_at?: string;
  companion_user_ids: number[];
  summary?: {
    stop_count?: number;
    duration_seconds?: number;
    rated_stop_count?: number;
  };
  stops: AdventourStop[];
  active_stop?: AdventourStop | null;
};
