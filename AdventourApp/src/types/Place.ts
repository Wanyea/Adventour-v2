export type Place = {
  place_id: string;
  provider?: string;
  provider_place_id?: string;
  request_id?: string;
  rank_position?: number;
  name: string;
  vicinity: string;
  types: string[];
  category?: 'food' | 'activity';
  tag_groups?: string[];
  diversity_groups?: string[];
  scoring_profile?: string;
  learned_score?: number;
  learned_rank_position?: number;
  explanation?: string;
  explanation_details?: {
    kind: string;
    label: string;
    value: string;
    strength?: number;
  }[];
  recommendation_story?: {
    headline?: string;
    reasons?: string[];
    cautions?: string[];
    authenticity_label?: string;
    authenticity_confidence_label?: string;
    confidence?: number;
    metrics?: {
      id: string;
      label: string;
      value?: number;
      display?: string;
    }[];
  };
  local_event_match?: {
    event_id?: number;
    title?: string;
    category?: string;
    starts_at?: string | null;
    ends_at?: string | null;
    distance_to_place_meters?: number | null;
    distance_from_launch_meters?: number | null;
    score?: number;
    fit_label?: string;
    source_name?: string;
    source_url?: string;
    reservation_url?: string;
    components?: {
      category_fit?: number;
      distance_fit?: number;
      source_fit?: number;
      reservation_fit?: number;
      authenticity?: number;
    };
  } | null;
  repeat_after_exhaustion?: boolean;
  history?: {
    recent_impressions?: number;
    accepted?: boolean;
    rejected?: boolean;
    friend_liked_by?: string[];
    friend_rejected_by?: string[];
  };
  score_components?: {
    scoring_profile?: string;
    novelty?: number;
    repeat_penalty?: number;
    decision_penalty?: number;
    chain_penalty?: number;
    price_penalty?: number;
    time_fit?: number;
    time_penalty?: number;
    exploration?: number;
    exploration_applied?: number;
    value_gem?: number;
    local_event_fit?: number;
    friend_history_fit?: number;
    friend_history_signal_count?: number;
  };
  ranking?: {
    strategy?: string;
    scoring_profile?: string;
    diversity_adjusted_score?: number;
    diversity_bonus?: number;
    diversity_penalty?: number;
    member_coverage_bonus?: number;
    party_coverage_rescue?: boolean;
    local_discovery_rescue?: boolean;
    rescued_member?: string;
    rescued_member_fit?: number;
    replaced_pick?: string;
    rescue_reason?: string;
    score_gap?: number;
    authenticity_gain?: number;
    learned_model_score?: number;
    learned_model_type?: string;
    served_new_members?: string[];
    preserved_top_pick?: boolean;
    exploration_budget?: {
      eligible?: boolean;
      allowed?: boolean;
      reason?: string;
      frontier_gap?: number;
      max_page_share?: number;
      max_exploratory?: number;
      friend_learning?: boolean;
      served_learning_members?: string[];
      authenticity_guardrail?: {
        allowed?: boolean;
        reason?: string;
        authenticity?: number;
        chain_probability?: number;
        tourist_trap_score?: number;
      };
    };
    objective_breakdown?: {
      model_family?: string;
      positive?: {
        id: string;
        label: string;
        component: number;
        weight: number;
        contribution: number;
      }[];
      penalties?: {
        id: string;
        label: string;
        penalty: number;
      }[];
      positive_total?: number;
      penalty_total?: number;
      net_score?: number;
      final_score?: number;
      top_positive?: string[];
      top_penalty?: string | null;
    };
  };
  authenticity_evidence?: {
    label?: string;
    score?: number;
    hidden_gem_score?: number;
    chain_risk?: number;
    tourist_trap_score?: number;
    popularity_score?: number;
    confidence?: number;
    confidence_status?: string;
    confidence_label?: string;
    rating_count?: number;
    evidence_signals?: string[];
    reasons?: string[];
  };
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
  member_fit?: {
    user_id: number;
    display_name: string;
    fit: number;
  }[];
  party_fit_summary?: {
    headline?: string;
    detail?: string;
    average_fit?: number;
    lowest_fit?: number;
    highest_fit?: number;
    fairness_score?: number;
    group_fit?: number;
    strong_members?: {
      user_id: number;
      display_name: string;
      fit: number;
    }[];
    weak_members?: {
      user_id: number;
      display_name: string;
      fit: number;
    }[];
    members?: {
      user_id: number;
      display_name: string;
      fit: number;
    }[];
  } | null;
};
