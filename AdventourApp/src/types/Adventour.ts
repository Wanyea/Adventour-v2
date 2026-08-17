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
  place_id: number;
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
  metadata?: Record<string, any>;
  display: AdventourStopDisplay;
};

export type TravelReservation = {
  id: number;
  user_id?: number;
  adventour_session_id?: number | null;
  reservation_type: string;
  title: string;
  provider?: string;
  confirmation_code?: string;
  starts_at?: string;
  ends_at?: string;
  cost_total?: number | null;
  currency?: string;
  booking_url?: string;
  notes?: string;
  metadata?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
};

export type AdventourBookingSummary = {
  status: 'empty' | 'needs_details' | 'partial' | 'ready';
  message: string;
  party_size: number;
  reservation_count: number;
  confirmation_count: number;
  booking_link_count: number;
  known_cost_count: number;
  currency: string;
  total_known_cost: number;
  known_cost_per_person: number;
  type_counts: Record<string, number>;
  type_costs: Record<string, number>;
  readiness_score: number;
};

export type AdventourDestinationScoutSummary = {
  source?: string;
  selected_destination?: {
    id?: string;
    label?: string;
    location?: {
      latitude?: number;
      longitude?: number;
    };
  };
  scoring_profile?: string;
  rank?: {
    trip_readiness_score?: number;
    authenticity_score?: number;
    event_actionability_score?: number;
    booking_handoff_score?: number;
  };
  explanation?: {
    headline?: string;
    tradeoffs?: {
      kind?: string;
      label?: string;
      value?: string;
      tone?: string;
    }[];
  };
};

export type AdventourSession = {
  id: number;
  title: string;
  status: 'active' | 'completed' | 'abandoned';
  started_at?: string;
  ended_at?: string;
  companion_user_ids: number[];
  summary?: {
    source?: string;
    destination?: string;
    scoring_profile?: string;
    trip_style?: string;
    pace?: string;
    budget_profile?: string;
    query_tags?: string[];
    route_readiness?: any;
    local_events?: any;
    destination_scout?: AdventourDestinationScoutSummary;
    filter_summary?: any;
    price_breakdown?: any;
    booking_plan?: any;
    stop_count?: number;
    duration_seconds?: number;
    rated_stop_count?: number;
    completion?: {
      stop_count?: number;
      duration_seconds?: number;
      rated_stop_count?: number;
    };
  };
  stops: AdventourStop[];
  active_stop?: AdventourStop | null;
  reservations?: TravelReservation[];
  booking_summary?: AdventourBookingSummary;
};
