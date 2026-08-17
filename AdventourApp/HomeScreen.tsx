import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Animated,
  View,
  Text,
  TextInput,
  Alert,
  TouchableOpacity,
  StyleSheet,
  Image,
  Linking,
  ScrollView,
} from 'react-native';
import RecommendationDeck from './src/components/RecommendationDeck';
import PlaceDetailsModal from './src/components/PlaceDetailsModal';
import AdventourJourneyPanel from './src/components/AdventourJourneyPanel';
import AdventourLaunchHero from './src/components/AdventourLaunchHero';
import GoogleAutocompleteService from './src/GoogleAutocompleteService';
import Config from './src/Config';
import Geolocation from '@react-native-community/geolocation';
import axios from 'axios';
import AsyncStorage from '@react-native-async-storage/async-storage';
import 'react-native-get-random-values';
import { v4 as uuidv4 } from 'uuid';
import { PermissionsAndroid, Platform } from 'react-native';
import { Place } from './src/types/Place';
import { AdventourSession, AdventourStop } from './src/types/Adventour';
import { TAG_GROUPS, tagGroupDisplayLabel, tagGroupIdsForPlace } from './src/placeTagGroups';
import AdventourService from './src/services/AdventourService';
import { User } from './src/services/AuthService';

type Coordinates = { latitude: number; longitude: number };
type LocationMode = 'none' | 'gps' | 'manual';
type DiscoverMode = 'spontaneous' | 'itinerary';
type RequestStep = 'geocode' | 'recommendations';
type RadiusOption = {
  id: 'walkable' | 'nearby' | 'explore' | 'wide';
  label: string;
  helper: string;
  meters: number;
};
type PlanOption = {
  id: 'day' | 'weekend' | 'vacation';
  label: string;
  helper: string;
  days: number;
};
type PaceOption = {
  id: 'relaxed' | 'balanced' | 'full';
  label: string;
  helper: string;
};
type BudgetOption = {
  id: 'budget' | 'flexible' | 'splurge';
  label: string;
  helper: string;
};
type LodgingOption = {
  id: 'flexible' | 'hotel' | 'home_share';
  label: string;
  helper: string;
};
type LocalTransportOption = {
  id: 'auto' | 'transit' | 'rideshare' | 'rental_car';
  label: string;
  helper: string;
};
type BackendScoringProfileId = 'phase1_balanced' | 'authenticity_forward' | 'group_friendly' | 'fresh_discovery' | 'event_anchor';
type ScoringProfileId = BackendScoringProfileId | 'auto_scout' | 'learned_beta';
type ScoringProfileOption = {
  id: ScoringProfileId;
  label: string;
  helper: string;
  backendProfileId?: BackendScoringProfileId;
  learnedRerank?: boolean;
};
const MAX_ITINERARY_DAYS = 7;
type FriendOption = {
  id: number;
  username: string;
  display_name: string;
  profile_picture?: string;
};
type PreferenceInsightEntry = {
  tag: string;
  label: string;
  weight: number;
};
type PreferenceInsight = {
  user_id: number;
  display_name: string;
  learning_status: 'cold_start' | 'learning' | 'personalized' | string;
  confidence: number;
  signal_count: number;
  event_counts?: Record<string, number>;
  top_categories?: PreferenceInsightEntry[];
  avoided_categories?: PreferenceInsightEntry[];
  top_cuisines?: PreferenceInsightEntry[];
  top_activities?: PreferenceInsightEntry[];
  avoid_chains?: number;
  hidden_gem_affinity?: number;
  price_preference?: number | null;
  last_signal_at?: string | null;
};
type GroupCompromiseBrief = {
  status?: 'unknown' | 'solo' | 'balanced' | 'covered_but_uneven' | 'needs_coverage' | 'uneven' | 'watch' | string;
  headline?: string;
  message?: string;
  dominant_member?: {
    user_id?: number | string;
    display_name?: string;
    average_fit?: number | null;
  } | null;
  most_compromised_member?: {
    user_id?: number | string;
    display_name?: string;
    average_fit?: number | null;
  } | null;
  fit_gap?: number | null;
  coverage_share?: number | null;
  fairness_score?: number | null;
  next_action?: string;
  balance_chips?: {
    label?: string;
    value?: string;
    tone?: 'positive' | 'caution' | 'neutral' | string;
  }[];
};
type GroupFitSummary = {
  member_count: number;
  average_fit: number;
  lowest_fit: number;
  fairness_score?: number | null;
  message?: string;
  covered_member_count?: number;
  coverage_share?: number;
  ready_for_friend_testing?: boolean;
  members?: {
    user_id: number;
    display_name: string;
    average_fit: number;
    matched_count: number;
    coverage_status?: 'covered' | 'needs_match' | string;
    best_fit?: number;
    best_match?: MemberCoveragePlace | null;
    strong_matches?: MemberCoveragePlace[];
    preferred_groups?: {
      id: string;
      label: string;
    }[];
    suggested_query_tags?: string[];
    learning_status?: 'cold_start' | 'learning' | 'personalized' | string;
    signal_count?: number;
    confidence?: number;
  }[];
  underserved_members?: {
    user_id: number;
    display_name: string;
    average_fit: number;
    matched_count: number;
    coverage_status?: 'covered' | 'needs_match' | string;
    best_fit?: number;
    best_match?: MemberCoveragePlace | null;
    strong_matches?: MemberCoveragePlace[];
    preferred_groups?: {
      id: string;
      label: string;
    }[];
    suggested_query_tags?: string[];
    learning_status?: 'cold_start' | 'learning' | 'personalized' | string;
    signal_count?: number;
    confidence?: number;
  }[];
  coverage_plan?: {
    status?: 'ready' | 'needs_member_coverage' | 'uneven' | 'watch' | string;
    headline?: string;
    covered_member_count?: number;
    coverage_share?: number;
    fairness_score?: number | null;
    ready_for_friend_testing?: boolean;
    cold_start_member_count?: number;
    next_actions?: string[];
  };
  compromise_brief?: GroupCompromiseBrief | null;
};
type MemberCoveragePlace = {
  place_id?: number;
  name?: string;
  rank_position?: number;
  fit?: number;
  score?: number;
  diversity_groups?: string[];
  authenticity_label?: string;
};
type SlateSummary = {
  status?: string;
  message?: string;
  metrics?: {
    returned?: number;
    unique_group_count?: number;
    target_group_count?: number;
    diversity_coverage?: number;
    dominant_group_share?: number;
    covered_intent_count?: number;
    missing_intent_count?: number;
    first_page_size?: number;
    first_page_unique_group_count?: number;
    first_page_diversity_coverage?: number;
    first_page_dominant_group_share?: number;
    first_page_covered_intent_count?: number;
    first_page_missing_intent_count?: number;
    member_coverage_share?: number | null;
  };
  first_page_group_counts?: Record<string, number>;
  first_page_covered_intent_groups?: string[];
  first_page_missing_intent_groups?: string[];
  member_coverage?: {
    user_id: number;
    display_name: string;
    strong_match_count: number;
    best_fit: number;
    best_match?: MemberCoveragePlace | null;
    strong_matches?: MemberCoveragePlace[];
  }[];
  underserved_members?: {
    user_id: number;
    display_name: string;
    strong_match_count: number;
    best_fit: number;
    best_match?: MemberCoveragePlace | null;
    strong_matches?: MemberCoveragePlace[];
  }[];
};
type FriendReadinessMember = {
  user_id?: number;
  display_name?: string;
  status?: 'covered' | 'needs_match' | string;
  coverage_status?: 'covered' | 'needs_match' | string;
  average_fit?: number | null;
  best_fit?: number | null;
  strong_match_count?: number;
  matched_count?: number;
  best_match?: MemberCoveragePlace | null;
  preferred_groups?: {
    id: string;
    label: string;
  }[];
  suggested_query_tags?: string[];
  learning_status?: 'cold_start' | 'learning' | 'personalized' | string;
  signal_count?: number;
  confidence?: number | null;
  suggested_swaps?: FriendSwapSuggestion[];
};
type FriendSwapSuggestion = {
  day?: number;
  slot_id?: string;
  slot_label?: string;
  from_stop?: string;
  to_stop?: string;
  fit?: number | null;
  current_fit?: number | null;
  member_fit_delta?: number | null;
  member_rebalance_delta?: number | null;
  current_group_consensus_fit?: number | null;
  group_consensus_fit?: number | null;
  group_consensus_delta?: number | null;
  current_group_consensus_gap?: number | null;
  group_consensus_gap?: number | null;
  group_consensus_gap_delta?: number | null;
  low_friction_score?: number | null;
  reason?: string | null;
};
type FriendReadinessSummary = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  member_count?: number;
  covered_member_count?: number;
  underserved_count?: number;
  coverage_share?: number | null;
  average_group_fit?: number | null;
  average_consensus_fit?: number | null;
  consensus_gap?: number | null;
  cold_start_member_count?: number;
  members?: FriendReadinessMember[];
  underserved_members?: FriendReadinessMember[];
  suggested_swaps?: FriendSwapSuggestion[];
  watchouts?: string[];
  next_actions?: string[];
};
type ScenarioReadinessCheck = {
  name: string;
  label: string;
  status: 'pass' | 'warn' | 'fail' | 'unknown' | string;
  value?: string | number | boolean | null;
  target?: string;
  message?: string;
};
type ScenarioReadinessSummary = {
  mode?: 'basket' | 'planned_itinerary' | string;
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  ready_for_friend_testing?: boolean;
  beta_testable?: boolean;
  headline?: string;
  test_verdict?: {
    status?: 'ready' | 'watch' | 'needs_attention' | string;
    headline?: string;
    score?: number | null;
    friend_testable?: boolean;
    dimensions?: {
      name?: string;
      label?: string;
      score?: number | null;
      status?: 'pass' | 'warn' | 'fail' | 'unknown' | string;
      summary?: string;
    }[];
    blockers?: string[];
    next_actions?: string[];
  };
  metrics?: Record<string, any>;
  checks?: ScenarioReadinessCheck[];
  strengths?: string[];
  warnings?: string[];
  next_actions?: string[];
  remediation_plan?: {
    id?: string;
    label?: string;
    severity?: 'watch' | 'needs_attention' | string;
    adjustment?: {
      kind?: 'rerun_recommendations'
        | 'collect_trip_inputs'
        | 'collect_feedback'
        | 'scout_local_events'
        | 'collect_event_social_signal'
        | 'collect_booking_details'
        | string;
      scoring_profile?: string;
      boost_query_tags?: string[];
      radius_multiplier?: number;
      clear_excluded_tag_groups?: boolean;
      required_inputs?: string[];
      reason?: string;
    } | null;
    actions?: string[];
  }[];
  friend_readiness?: FriendReadinessSummary | null;
};
type BasketDecisionSummary = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  score?: number | null;
  dimensions?: {
    name?: string;
    label?: string;
    score?: number | null;
    status?: 'pass' | 'warn' | 'fail' | 'unknown' | string;
    summary?: string;
    next_action?: string;
  }[];
  strengths?: string[];
  warnings?: string[];
  next_actions?: string[];
};
type ModelConfidenceSummary = {
  status?: 'ready' | 'learning' | 'cold_start' | string;
  headline?: string;
  score?: number | null;
  learning_status?: 'cold_start' | 'learning' | 'personalized' | string;
  average_preference_confidence?: number;
  average_signal_count?: number;
  member_count?: number;
  local_feeling_share?: number;
  member_coverage_share?: number | null;
  stop_coverage?: number;
  authenticity_score?: number;
  party_score?: number;
  booking_score?: number;
  swap_coverage?: number;
  exploration_count?: number;
  exploration_eligible_count?: number;
  serendipity_score?: number | null;
  learned_rerank?: {
    applied?: boolean;
    reason?: string | null;
    model_type?: string | null;
    guard_status?: string | null;
    guard_headline?: string | null;
  };
  basis?: string[];
  warnings?: string[];
  next_actions?: string[];
};
type RecommendationQualitySummary = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  metrics?: {
    returned?: number;
    raw_candidates?: number;
    average_score?: number;
    average_authenticity?: number;
    local_feeling_count?: number;
    local_feeling_share?: number;
    hidden_gem_count?: number;
    hidden_gem_share?: number;
    generic_risk_count?: number;
    generic_risk_share?: number;
    average_authenticity_confidence?: number;
    thin_local_evidence_count?: number;
    value_gem_count?: number;
    value_gem_share?: number;
    friend_history_positive_count?: number;
    friend_history_conflict_count?: number;
    friend_history_signal_count?: number;
    friend_history_signal_share?: number;
    exploration_count?: number;
    exploration_eligible_count?: number;
    exploration_share?: number;
    serendipity_score?: number;
    serendipity_target_min?: number;
    serendipity_target_max?: number;
    serendipity_safe_count?: number;
    serendipity_blocked_count?: number;
    local_event_backed_count?: number;
    local_event_backed_share?: number;
    local_event_reservation_ready_count?: number;
    local_event_source_ready_count?: number;
    local_event_friend_signal_count?: number;
    local_event_community_signal_count?: number;
    local_event_social_score?: number;
    party_coverage_rescue_count?: number;
    party_coverage_rescued_members?: string[];
    average_group_fit?: number | null;
    diversity_coverage?: number | null;
    dominant_group_share?: number | null;
    missing_intent_count?: number;
    first_page_diversity_coverage?: number | null;
    first_page_dominant_group_share?: number | null;
    first_page_missing_intent_count?: number;
    first_page_local_discovery_count?: number;
    local_discovery_rescue_count?: number;
    member_coverage_share?: number | null;
    provider_error_count?: number;
    repeated_decided?: boolean;
  };
  strengths?: string[];
  warnings?: string[];
  checks?: ScenarioReadinessCheck[];
  next_actions?: string[];
  ready_for_friend_testing?: boolean;
  beta_testable?: boolean;
  remediation_plan?: ScenarioReadinessSummary['remediation_plan'];
  friend_readiness?: FriendReadinessSummary | null;
  test_verdict?: ScenarioReadinessSummary['test_verdict'];
  decision_summary?: BasketDecisionSummary | null;
  model_confidence?: ModelConfidenceSummary | null;
  serendipity_plan?: {
    status?: 'empty' | 'under_target' | 'balanced' | 'over_target' | string;
    headline?: string;
    message?: string;
    score?: number;
    target_min?: number;
    target_max?: number;
    allowed_count?: number;
    eligible_count?: number;
    safe_count?: number;
    blocked_count?: number;
    friend_learning?: boolean;
    served_learning_members?: string[];
    blocked_reasons?: {
      reason?: string;
      count?: number;
    }[];
    learning_picks?: {
      place_id?: number | string;
      name?: string;
      score?: number;
      authenticity_label?: string;
      exploration?: number;
      frontier_gap?: number;
      reason?: string;
    }[];
    next_action?: string;
    research_basis?: string[];
  } | null;
  diagnostic?: {
    status?: 'ready' | 'watch' | 'needs_attention' | string;
    headline?: string;
    primary_issue?: {
      name?: string;
      label?: string;
      status?: 'pass' | 'warn' | 'fail' | 'unknown' | string;
      score?: number | null;
      summary?: string;
      next_action?: string;
    } | null;
    stages?: {
      name?: string;
      label?: string;
      status?: 'pass' | 'warn' | 'fail' | 'unknown' | string;
      score?: number | null;
      summary?: string;
      next_action?: string;
    }[];
    next_actions?: string[];
    summary?: {
      raw_candidates?: number;
      returned?: number;
      total_skipped?: number;
      provider_error_count?: number;
    };
  } | null;
};
type ItineraryRecommendation = {
  place_id: number;
  name: string;
  latitude?: number;
  longitude?: number;
  score?: number;
  diversity_groups?: string[];
  components?: {
    authenticity?: number;
    authenticity_confidence?: number;
    authenticity_confidence_status?: string;
    quality?: number;
    group_fit?: number;
    group_member_count?: number;
    group_min_fit?: number;
    chain_penalty?: number;
    price_penalty?: number;
    friend_history_fit?: number;
  };
  history?: {
    friend_liked_by?: string[];
    friend_rejected_by?: string[];
  };
  ranking?: {
    party_coverage_rescue?: boolean;
    local_discovery_rescue?: boolean;
    rescued_member?: string;
    rescued_member_fit?: number;
    replaced_pick?: string;
    rescue_reason?: string;
    score_gap?: number;
    authenticity_gain?: number;
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
  explanation_details?: {
    kind?: string;
    label?: string;
    value?: string;
    strength?: number;
  }[];
  swap_impact?: {
    route_score_delta?: number;
    authenticity_delta?: number;
    member_fit_delta?: number;
    group_consensus_delta?: number;
    group_consensus_gap_delta?: number;
    current_group_consensus_fit?: number;
    replacement_group_consensus_fit?: number;
    current_group_consensus_gap?: number;
    replacement_group_consensus_gap?: number;
    target_members?: {
      user_id?: number | string;
      display_name?: string;
      current_fit?: number;
      replacement_fit?: number;
      delta?: number;
      coverage_status?: string;
    }[];
    weakened_members?: {
      user_id?: number | string;
      display_name?: string;
      current_fit?: number;
      replacement_fit?: number;
      delta?: number;
      coverage_status?: string;
    }[];
    variety_delta?: number;
    travel_efficiency_delta?: number;
    member_rebalance_delta?: number;
    friend_history_delta?: number;
    current_friend_history_fit?: number;
    replacement_friend_history_fit?: number;
    friend_signal?: {
      status?: 'positive' | 'caution' | 'neutral' | string;
      label?: string;
      message?: string | null;
      current_liked_by?: string[];
      current_rejected_by?: string[];
      replacement_liked_by?: string[];
      replacement_rejected_by?: string[];
    };
    travel_distance_meters?: number | null;
    slot_fit_delta?: number;
    price_level_delta?: number | null;
    known_cost_delta_low?: number | null;
    known_cost_delta_high?: number | null;
    cost_impact_status?: 'saves' | 'similar' | 'pricier' | 'unknown' | string;
    cost_impact_label?: string;
    cost_impact_detail?: string;
    low_friction_score?: number;
    low_friction_label?: string;
    reasons?: string[];
    swap_readiness?: {
      status?: 'safe_upgrade' | 'party_rebalance' | 'balanced_tradeoff' | 'route_risk' | string;
      label?: string;
      score?: number;
      low_friction_score?: number;
      low_friction_label?: string;
      next_action?: string;
    };
    swap_decision?: {
      headline?: string;
      should_swap?: boolean;
      best_when?: string;
      tradeoff?: string;
      primary_reason?: string;
      confidence?: number;
      low_friction_score?: number;
      low_friction_label?: string;
      badges?: {
        label?: string;
        detail?: string;
        tone?: 'positive' | 'neutral' | 'caution' | string;
        names?: string[];
      }[];
    };
  };
  member_fit?: {
    user_id: number;
    display_name: string;
    fit: number;
  }[];
  display?: {
    name?: string;
    vicinity?: string;
    latitude?: number;
    longitude?: number;
    price_level?: number;
    types?: string[];
  };
};
type ItineraryStop = {
  slot_id: string;
  label: string;
  time_window: string;
  role: string;
  recommendation: ItineraryRecommendation;
  why_this_stop?: {
    headline?: string;
    reasons?: string[];
    cautions?: string[];
    stats?: {
      route_score?: number;
      slot_matches?: number;
      authenticity?: number;
      hidden_gem_score?: number;
      chain_risk?: number;
      travel_distance_meters?: number | null;
      member_fit?: number;
      rescued_member_fit?: number | null;
      friend_history_fit?: number;
    };
  };
  party_fit_summary?: {
    headline?: string;
    top_members?: {
      user_id: number;
      display_name: string;
      fit: number;
    }[];
    weak_members?: {
      user_id: number;
      display_name: string;
      fit: number;
    }[];
    average_fit?: number | null;
    lowest_fit?: number | null;
    highest_fit?: number | null;
    coverage_rescue?: {
      member?: string;
      fit?: number | null;
      replaced_pick?: string;
      reason?: string;
      score_gap?: number;
    } | null;
  };
  alternatives: ItineraryRecommendation[];
  diversity_groups?: string[];
  local_event_matches?: StopLocalEventMatch[];
  swap_history?: {
    swapped: boolean;
    swapped_at?: string;
    from_place_id?: number;
    from_name?: string;
    to_place_id?: number;
    to_name?: string;
    impact?: ItineraryRecommendation['swap_impact'];
  };
};
type SwapGuide = {
  status?: 'ready' | 'watch' | 'needs_attention' | 'needs_route' | string;
  headline?: string;
  next_action?: string;
  stop_count?: number;
  swappable_stop_count?: number;
  swap_coverage?: number;
  alternative_count?: number;
  recommended_swap_count?: number;
  low_friction_count?: number;
  authenticity_upgrade_count?: number;
  party_upgrade_count?: number;
  consensus_upgrade_count?: number;
  route_risk_count?: number;
  cost_caution_count?: number;
  cost_saving_count?: number;
  party_coverage_plan?: {
    status?: string;
    headline?: string;
    next_action?: string;
    member_count?: number;
    underserved_member_count?: number;
    actionable_member_count?: number;
    members?: {
      user_id?: number | string;
      display_name?: string;
      average_fit?: number | null;
      coverage_status?: string | null;
      strong_match_count?: number;
      suggested_swaps?: {
        day?: number;
        slot_id?: string;
        slot_label?: string;
        from_name?: string;
        to_name?: string;
        to_place_id?: number | string;
        confidence?: number | null;
        low_friction_score?: number | null;
        replacement_fit?: number | null;
        fit_delta?: number | null;
        coverage_status?: string;
        tradeoff?: string;
      }[];
    }[];
  };
  best_swaps?: {
    day?: number;
    slot_id?: string;
    slot_label?: string;
    from_place_id?: number | string;
    from_name?: string;
    to_place_id?: number | string;
    to_name?: string;
    headline?: string;
    best_when?: string;
    tradeoff?: string;
    should_swap?: boolean;
    confidence?: number | null;
    low_friction_score?: number | null;
    low_friction_label?: string;
    route_score_delta?: number | null;
    authenticity_delta?: number | null;
    member_fit_delta?: number | null;
    member_rebalance_delta?: number | null;
    group_consensus_delta?: number | null;
    group_consensus_gap_delta?: number | null;
    target_members?: {
      user_id?: number | string;
      display_name?: string;
      current_fit?: number;
      replacement_fit?: number;
      delta?: number;
      coverage_status?: string;
    }[];
    weakened_members?: {
      user_id?: number | string;
      display_name?: string;
      current_fit?: number;
      replacement_fit?: number;
      delta?: number;
      coverage_status?: string;
    }[];
    travel_efficiency_delta?: number | null;
    travel_distance_meters?: number | null;
    price_level_delta?: number | null;
    known_cost_delta_low?: number | null;
    known_cost_delta_high?: number | null;
    cost_impact_status?: string | null;
    cost_impact_label?: string | null;
    cost_impact_detail?: string | null;
    status?: string;
    reasons?: string[];
    badges?: {
      label?: string;
      detail?: string;
      tone?: 'positive' | 'neutral' | 'caution' | string;
    }[];
  }[];
};
type BookingComponent = {
  id: string;
  type: string;
  label: string;
  status: string;
  mode?: string;
  nights?: number;
  estimated_segments?: number;
  route_distance_meters?: number | null;
  estimate?: {
    currency: string;
    per_person_low: number;
    per_person_high: number;
  } | null;
  options?: {
    id: string;
    label: string;
    recommended: boolean;
    estimate: {
      currency: string;
      per_person_low: number;
      per_person_high: number;
    };
    setup: string;
    why: string;
  }[];
  action?: string;
  setup?: string;
  setup_provider?: string | null;
  setup_source_url?: string | null;
  setup_steps?: string[];
  required_inputs?: string[];
  missing_inputs?: string[];
  next_steps?: string[];
  search_hint?: string;
  provider_options?: {
    label: string;
    url?: string | null;
    note?: string;
  }[];
  stores_reservation?: boolean;
};
type BookingSummary = {
  readiness_score?: number;
  ready_component_count?: number;
  provider_action_count?: number;
  blocked_component_count?: number;
  missing_input_count?: number;
  missing_inputs?: string[];
  estimate_ready_count?: number;
  reservation_storage_ready?: boolean;
  duration_alignment_status?: string;
  duration_alignment_message?: string;
  message?: string;
};
type BookingDurationAlignment = {
  status?: string;
  severity?: string;
  headline?: string;
  message?: string;
  next_action?: string | null;
  trip_style?: string;
  route_days?: number;
  calendar_nights?: number;
  has_date_range?: boolean;
};
type TripStyleFit = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  message?: string;
  score?: number;
  trip_style?: string;
  suggested_style?: string;
  style_label?: string;
  route_days?: number;
  nights?: number;
  duration_fit?: number;
  route_depth_score?: number;
  booking_score?: number;
  quote_coverage?: number;
  quote_required_count?: number;
  quote_ready_count?: number;
  event_density?: number;
  event_route_match_count?: number;
  reasons?: string[];
  cautions?: string[];
  next_action?: string;
};
type BookingPrepChecklist = {
  status?: string;
  headline?: string;
  items?: {
    id: string;
    label: string;
    status: 'ready' | 'action_needed' | 'manual' | 'optional' | string;
    priority?: number;
    detail?: string;
    action?: string;
    component_type?: string;
    provider?: string | null;
    source_url?: string | null;
    estimate?: {
      currency: string;
      per_person_low: number;
      per_person_high: number;
    } | null;
  }[];
};
type BookingPlanningBurden = {
  level?: 'low' | 'medium' | 'high' | string;
  score?: number;
  headline?: string;
  next_action?: string;
  action_needed_count?: number;
  manual_count?: number;
  optional_count?: number;
  setup_count?: number;
  provider_action_count?: number;
  highest_friction_item?: {
    id?: string;
    label?: string;
    status?: string;
    detail?: string;
    action?: string;
    component_type?: string;
    source_url?: string | null;
  } | null;
  setup_items?: {
    type?: string;
    label?: string;
    provider?: string;
    detail?: string;
    source_url?: string | null;
  }[];
  booking_order?: {
    id?: string;
    label?: string;
    status?: string;
    detail?: string;
    action?: string;
    component_type?: string;
    source_url?: string | null;
  }[];
};
type BookingActionLink = {
  id?: string;
  component_type?: string;
  label?: string;
  status?: string;
  provider_label?: string;
  url?: string | null;
  note?: string;
  search_hint?: string;
  stores_reservation?: boolean;
  reservation_type?: string;
  draft_title?: string;
  draft_provider?: string;
  draft_booking_url?: string | null;
  draft_notes?: string;
};
type BookingHandoff = {
  status?: 'ready' | 'needs_details' | 'manual' | string;
  headline?: string;
  next_step?: string;
  readiness_score?: number;
  ready_to_quote_count?: number;
  ready_to_save_count?: number;
  missing_input_count?: number;
  quote_ready?: BookingActionLink[];
  save_ready?: BookingActionLink[];
  setup_ready?: {
    id?: string;
    component_type?: string;
    label?: string;
    provider_label?: string | null;
    url?: string | null;
    estimate?: {
      currency?: string;
      per_person_low?: number | null;
      per_person_high?: number | null;
    } | null;
    recommended_option?: {
      id?: string;
      label?: string;
      why?: string;
    } | null;
  }[];
  required_inputs?: {
    id?: string;
    label?: string;
    component_type?: string;
  }[];
};
type BookingChecklist = {
  status?: 'ready' | 'ready_with_manual_steps' | 'needs_details' | string;
  headline?: string;
  readiness_score?: number;
  blocking_count?: number;
  ready_count?: number;
  action_count?: number;
  next_action?: string;
  items?: {
    id?: string;
    label?: string;
    status?: 'ready' | 'action_needed' | 'manual' | 'optional' | string;
    detail?: string;
    action?: string;
    blocking?: boolean;
    missing_inputs?: string[];
    link_count?: number;
    quote_ready_count?: number;
    save_ready_count?: number;
    required_count?: number;
    saved_count?: number;
    confirmed_count?: number;
    missing_labels?: string[];
    provider?: string | null;
    source_url?: string | null;
  }[];
};
type TripFriendTestPacket = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  score?: number | null;
  friend_testable?: boolean;
  beta_testable?: boolean;
  member_count?: number;
  covered_member_count?: number;
  underserved_count?: number;
  coverage_share?: number | null;
  average_group_fit?: number | null;
  friend_readiness_status?: string;
  friend_readiness_headline?: string;
  blockers?: string[];
  next_actions?: string[];
  dimensions?: NonNullable<ScenarioReadinessSummary['test_verdict']>['dimensions'];
  suggested_swaps?: FriendSwapSuggestion[];
  compromise_brief?: GroupCompromiseBrief | null;
};
type QuotePlan = {
  status?: string;
  headline?: string;
  message?: string;
  required_count?: number;
  ready_count?: number;
  missing_inputs?: string[];
  items?: {
    type?: string;
    label?: string;
    status?: string;
    quote_required?: boolean;
    quote_status?: string;
    missing_inputs?: string[];
    search_hint?: string | null;
    provider_options?: {
      label?: string | null;
      url?: string | null;
      note?: string | null;
    }[];
    primary_provider_label?: string | null;
    primary_url?: string | null;
    next_steps?: string[];
  }[];
};
type TripPacket = {
  status?: 'ready' | 'action_needed' | 'needs_details' | 'blocked' | string;
  headline?: string;
  can_start?: boolean;
  booking_score?: number;
  currency?: string;
  party_size?: number;
  known_per_person?: {
    low?: number | null;
    high?: number | null;
    label?: string | null;
  };
  cost_confidence?: {
    status?: 'estimated' | 'partially_saved' | 'saved' | string;
    tracked_total?: number;
    estimate_add_on_total?: number;
    estimate_add_on_per_person?: number;
    combined_known_low?: number | null;
    combined_known_high?: number | null;
    combined_label?: string | null;
    currency?: string;
    add_on_types?: string[];
    unknown_types?: string[];
    quote_status?: string;
    quote_required_count?: number;
    quote_ready_count?: number;
    quote_plan?: QuotePlan;
    message?: string;
  };
  quote_plan?: QuotePlan;
  trip_logistics_readiness?: {
    status?: 'ready' | 'action_needed' | 'needs_details' | 'manual' | string;
    headline?: string;
    score?: number;
    booking_readiness_score?: number;
    booking_handoff_status?: string | null;
    booking_checklist_status?: string | null;
    provider_link_count?: number;
    save_ready_count?: number;
    saveable_timeline_count?: number;
    setup_ready_count?: number;
    blocking_count?: number;
    action_count?: number;
    missing_input_count?: number;
    missing_inputs?: string[];
    checklist_ready_share?: number;
    reservation_storage_ready?: boolean;
    local_transport_status?: string | null;
    local_transport_mode?: string | null;
    local_transport_provider?: string | null;
    flight_status?: string | null;
    stay_status?: string | null;
    known_cost_ready?: boolean;
    known_per_person_low?: number | null;
    known_per_person_high?: number | null;
    unknown_cost_components?: string[];
    quote_status?: string;
    quote_required_count?: number;
    quote_ready_count?: number;
    quote_missing_inputs?: string[];
    strengths?: string[];
    warnings?: string[];
    next_actions?: string[];
  };
  trip_style_fit?: TripStyleFit;
  missing_inputs?: string[];
  reservation_coverage?: {
    required_count?: number;
    saved_count?: number;
    confirmed_count?: number;
    attached_count?: number;
    missing_labels?: string[];
    items?: {
      id?: string;
      label?: string;
      reservation_types?: string[];
      saved_count?: number;
      confirmed_count?: number;
      status?: string;
    }[];
    summary?: {
      status?: string;
      message?: string;
      reservation_count?: number;
      confirmation_count?: number;
      booking_link_count?: number;
      known_cost_count?: number;
      total_known_cost?: number;
      known_cost_per_person?: number;
      currency?: string;
      readiness_score?: number;
    };
  };
  quick_stats?: {
    id?: string;
    label?: string;
    value?: string | number | null;
    status?: string;
  }[];
  required_actions?: {
    id?: string;
    label?: string;
    detail?: string;
    status?: string;
  }[];
  booking_links?: {
    id?: string;
    label?: string;
    provider_label?: string;
    url?: string | null;
    stores_reservation?: boolean;
    reservation_type?: string;
  }[];
  save_prompts?: {
    id?: string;
    label?: string;
    detail?: string;
    reservation_type?: string;
    provider?: string | null;
    source_url?: string | null;
    reservation_url?: string | null;
    starts_at?: string | null;
    route_context?: {
      day?: number;
      slot_id?: string;
      fit_label?: string;
      distance_to_stop_meters?: number | null;
    } | null;
  }[];
  booking_command_center?: {
    status?: 'ready' | 'action_needed' | 'needs_details' | 'manual' | string;
    headline?: string;
    primary_action?: {
      id?: string;
      phase?: string;
      label?: string;
      detail?: string;
      status?: string;
      action?: string;
      component_type?: string;
      reservation_type?: string;
      provider_label?: string | null;
      source_url?: string | null;
      priority?: number;
      can_open?: boolean;
      can_save?: boolean;
    } | null;
    commands?: {
      id?: string;
      phase?: string;
      label?: string;
      detail?: string;
      status?: string;
      action?: string;
      component_type?: string;
      reservation_type?: string;
      provider_label?: string | null;
      source_url?: string | null;
      priority?: number;
      can_open?: boolean;
      can_save?: boolean;
    }[];
    command_count?: number;
    ready_count?: number;
    action_needed_count?: number;
    open_link_count?: number;
    save_prompt_count?: number;
    checklist_status?: string;
    trip_logistics_status?: string;
    booking_handoff_status?: string;
  };
  mobility_setup?: {
    status?: string;
    mode?: string;
    label?: string;
    provider?: string | null;
    provider_label?: string;
    source_url?: string | null;
    can_save?: boolean;
    reservation_type?: string;
    draft_title?: string;
    draft_provider?: string;
    draft_booking_url?: string | null;
    draft_notes?: string;
    route_distance_meters?: number | null;
    estimate?: {
      currency?: string;
      per_person_low?: number | null;
      per_person_high?: number | null;
    } | null;
    recommended_option?: {
      id?: string;
      label?: string;
      why?: string;
    } | null;
    setup_steps?: string[];
    next_step?: string;
  } | null;
  booking_checklist?: BookingChecklist;
  authenticity_packet?: RouteAuthenticityPacket;
  event_packet?: TripEventPacket;
  friend_test_packet?: TripFriendTestPacket;
  swap_guide?: SwapGuide;
  route_model_confidence?: ModelConfidenceSummary;
  beta_readiness?: {
    status?: 'ready' | 'beta_ready_with_notes' | 'needs_tuning' | 'not_ready' | string;
    headline?: string;
    score?: number;
    ready_for_friend_testing?: boolean;
    member_count?: number;
    weakest_dimension?: {
      id?: string;
      label?: string;
      score?: number;
      status?: string;
      action?: string;
    } | null;
    blocking_count?: number;
    watch_count?: number;
    dimensions?: {
      id?: string;
      label?: string;
      score?: number;
      weight?: number;
      status?: 'pass' | 'watch' | 'fail' | string;
      optional?: boolean;
      evidence?: string;
      action?: string;
    }[];
    strengths?: string[];
    required_actions?: string[];
    watchouts?: string[];
    next_action?: string;
  };
  next_step?: string;
  reservation_storage_ready?: boolean;
};
type RouteAuthenticityPacket = {
  status?: 'ready' | 'watch' | 'needs_attention' | string;
  headline?: string;
  score?: number;
  stop_count?: number;
  average_authenticity?: number;
  local_feeling_count?: number;
  hidden_gem_count?: number;
  generic_risk_count?: number;
  chain_risk_count?: number;
  tourist_trap_risk_count?: number;
  thin_local_evidence_count?: number;
  thin_local_evidence_share?: number;
  average_authenticity_confidence?: number;
  local_feeling_share?: number;
  hidden_gem_share?: number;
  generic_risk_share?: number;
  strongest_local_stops?: {
    slot_id?: string;
    label?: string;
    name?: string;
    authenticity?: number;
    authenticity_label?: string;
    hidden_gem_score?: number;
    chain_risk?: number;
    tourist_trap_score?: number;
    authenticity_confidence?: number | null;
    authenticity_confidence_status?: string;
  }[];
  risk_stops?: {
    slot_id?: string;
    label?: string;
    name?: string;
    authenticity?: number;
    authenticity_label?: string;
    hidden_gem_score?: number;
    chain_risk?: number;
    tourist_trap_score?: number;
    authenticity_confidence?: number | null;
    authenticity_confidence_status?: string;
  }[];
  highlights?: string[];
  warnings?: string[];
  next_actions?: string[];
};
type LocalEventSocialReadiness = {
  status?: 'ready' | 'watch' | 'needs_signal' | 'needs_scouting' | string;
  headline?: string;
  score?: number;
  event_count?: number;
  friend_signal_count?: number;
  community_signal_count?: number;
  friend_going_count?: number;
  friend_interested_count?: number;
  going_count?: number;
  interested_count?: number;
  social_anchor_count?: number;
  reservation_ready_count?: number;
  meetup_ready?: boolean;
  top_social_event?: {
    id?: number;
    title?: string;
    reservation_url?: string | null;
    source_url?: string | null;
  } | null;
  next_action?: string;
  blocking_count?: number;
  meetup_checklist?: {
    id?: string;
    label?: string;
    status?: 'ready' | 'watch' | 'missing' | 'research' | 'manual' | string;
    detail?: string;
    action?: string;
    blocking?: boolean;
  }[];
};
type LocalEventPlan = {
  status?: 'ready' | 'needs_confirmation' | 'needs_scouting' | string;
  headline?: string;
  items?: {
    id: string;
    label: string;
    status: 'ready' | 'research' | 'social' | 'optional' | 'manual' | string;
    priority?: number;
    detail?: string;
    action?: string;
    event_id?: number;
    source_badge?: string | null;
    source_url?: string | null;
    reservation_url?: string | null;
  }[];
};
type LocalEventSummary = {
  event_count?: number;
  top_score?: number;
  average_score?: number;
  readiness_score?: number;
  reservation_ready_count?: number;
  sourced_count?: number;
  interested_count?: number;
  going_count?: number;
  friend_interested_count?: number;
  friend_going_count?: number;
  social_anchor_count?: number;
  social_readiness?: LocalEventSocialReadiness;
  route_match_count?: number;
  route_reservation_ready_count?: number;
  route_actionable_event_count?: number;
  route_social_anchor_count?: number;
  route_friend_signal_count?: number;
  route_community_signal_count?: number;
  top_route_event_title?: string | null;
  top_route_social_event_title?: string | null;
  route_social_anchor?: {
    id?: number | string;
    title?: string;
    category?: string;
    score?: number;
    event_score?: number;
    reason?: string;
    action_url?: string | null;
    reservation_url?: string | null;
    source_url?: string | null;
    reservation_ready?: boolean;
    friend_signal_count?: number;
    community_signal_count?: number;
    source_badge?: string | null;
    route_context?: {
      day?: number;
      slot_id?: string;
      slot_label?: string;
      time_window?: string;
      stop_name?: string;
      fit_label?: string;
      distance_to_stop_meters?: number | null;
      route_fit?: number;
    } | null;
  } | null;
  route_context_message?: string;
  source_mix?: Record<string, number>;
  source_summary?: {
    trusted_source_count?: number;
    unsourced_count?: number;
    reservation_ready_count?: number;
    route_match_count?: number;
    top_route_event_title?: string | null;
    route_context_message?: string;
    source_mix?: Record<string, number>;
    source_badges?: {
      kind: string;
      badge: string;
      count: number;
    }[];
    external_source_count?: number;
    actionable_external_source_count?: number;
    external_source_types?: string[];
    recommended_external_source?: {
      label?: string;
      source_type?: string;
      url?: string | null;
      query?: string | null;
      reason?: string;
      goal?: string;
    };
    scouting_brief?: {
      status?: string;
      headline?: string;
      detail?: string;
      next_action?: string;
      goal?: string;
      recommended_source?: {
        label?: string;
        source_type?: string;
        url?: string | null;
        query?: string | null;
        reason?: string;
      } | null;
      missing?: {
        id?: string;
        label?: string;
        blocking?: boolean;
        action?: string;
      }[];
      blocking_count?: number;
      actionable_source_count?: number;
    };
    message?: string;
  };
  top_event_title?: string | null;
};
type TripEventPacket = {
  status?: 'ready' | 'needs_confirmation' | 'needs_scouting' | string;
  headline?: string;
  score?: number | null;
  social_status?: string;
  social_score?: number | null;
  event_plan_status?: string;
  short_label?: string;
  event_count?: number;
  route_match_count?: number;
  reservation_ready_count?: number;
  friend_signal_count?: number;
  community_signal_count?: number;
  top_event_title?: string | null;
  top_event?: LocalEventSocialReadiness['top_social_event'];
  route_social_anchor?: LocalEventSummary['route_social_anchor'];
  meetup_anchor?: {
    id?: number | string;
    title?: string;
    category?: string;
    starts_at?: string | null;
    source_name?: string | null;
    source_badge?: string | null;
    source_url?: string | null;
    reservation_url?: string | null;
    action_url?: string | null;
    reservation_ready?: boolean;
    friend_signal_count?: number;
    community_signal_count?: number;
    score?: number;
    reason?: string;
    next_action?: string;
    route_context?: {
      day?: number;
      slot_id?: string;
      slot_label?: string;
      time_window?: string;
      stop_name?: string;
      fit_label?: string;
      distance_to_stop_meters?: number | null;
      route_fit?: number;
    } | null;
  } | null;
  next_action?: string;
  meetup_checklist?: LocalEventSocialReadiness['meetup_checklist'];
  blocking_count?: number;
  recommended_source?: NonNullable<LocalEventSummary['source_summary']>['recommended_external_source'];
  event_plan_items?: NonNullable<LocalEventPlan['items']>;
};
type RecommendationFilterSummary = {
  raw_candidates?: number;
  returned?: number;
  skipped?: {
    hard_constraints?: number;
    distance?: number;
    decided?: number;
    not_discoverable?: number;
    duplicates?: number;
    non_positive_score?: number;
    local_authenticity_guardrail?: number;
  };
  hard_constraints_active?: boolean;
  excluded_tag_groups?: string[];
  included_tag_groups?: string[];
};
type RetrievalContext = {
  query_tags?: string[];
  boost_query_tags?: string[];
  boosted_query_tags?: string[];
  friend_adjusted?: boolean;
};
type SessionContextTag = {
  tag?: string;
  label?: string;
  weight?: number;
};
type SessionContextSummary = {
  status?: 'active' | 'empty' | string;
  window_hours?: number;
  signal_count?: number;
  positive_signal_count?: number;
  negative_signal_count?: number;
  top_positive_tags?: SessionContextTag[];
  top_negative_tags?: SessionContextTag[];
  last_signal_at?: string | null;
};
type LearnedTrainingDataHealthCheck = {
  name?: string;
  label?: string;
  status?: 'pass' | 'warn' | 'fail' | string;
  value?: unknown;
  target?: string;
  message?: string;
};
type LearnedTrainingDataHealth = {
  status?: 'ready' | 'watch' | 'needs_data' | 'unknown' | string;
  summary?: string;
  counts?: {
    examples?: number;
    labeled?: number;
    positive?: number;
    negative?: number;
    requests?: number;
    group_examples?: number;
    friend_adjusted?: number;
    event_backed?: number;
    event_reservation_ready?: number;
    event_source_ready?: number;
    event_friend_signal?: number;
    event_social_signal?: number;
  };
  checks?: LearnedTrainingDataHealthCheck[];
  blocking_checks?: LearnedTrainingDataHealthCheck[];
  watch_checks?: LearnedTrainingDataHealthCheck[];
};
type LearnedRerankSummary = {
  applied: boolean;
  available?: boolean;
  ready?: boolean;
  status?: string;
  reason?: string;
  message?: string;
  model_type?: string;
  recommendation_count?: number;
  override_applied?: boolean;
  override_available?: boolean;
  feature_compatibility?: {
    status?: 'pass' | 'fail' | string;
    reason?: string;
    message?: string;
    feature_schema_version?: string | null;
    expected_feature_schema_version?: string;
    model_feature_count?: number;
    expected_feature_count?: number;
    missing_features?: string[];
    extra_features?: string[];
  };
  runtime_guard?: {
    status?: 'pass' | 'watch' | 'constrained' | string;
    headline?: string;
    counts?: {
      pass?: number;
      warn?: number;
      fail?: number;
    };
  };
  promotion_gate?: {
    status?: string;
    can_promote?: boolean;
    summary?: string;
    checks?: {
      name?: string;
      label?: string;
      status?: string;
      value?: string;
      message?: string;
    }[];
  };
  training_data_health?: LearnedTrainingDataHealth;
};
type ItineraryPlan = {
  request_id?: string;
  scoring_profile?: ScoringProfileOption['id'] | string;
  available_scoring_profiles?: string[];
  comparison_profile?: ScoringProfileOption['id'] | string;
  comparison_destination?: DestinationCandidate;
  comparison_destination_rank?: ItineraryComparison['comparison_rank'];
  comparison_destination_explanation?: ItineraryComparison['comparison_explanation'];
  learned_rerank?: LearnedRerankSummary;
  preference_insights?: PreferenceInsight[];
  recommendation_quality?: RecommendationQualitySummary | null;
  route_model_confidence?: ModelConfidenceSummary;
  trip_logistics_readiness?: TripPacket['trip_logistics_readiness'];
  trip_style_fit?: TripStyleFit;
  title: string;
  destination?: string;
  trip_style?: string;
  pace?: string;
  budget_profile?: string;
  nights?: number;
  member_count: number;
  query_tags?: string[];
  retrieval_context?: RetrievalContext;
  days: {
    day: number;
    title: string;
    summary: string;
    route_balance?: {
      unique_groups?: string[];
      group_counts?: Record<string, number>;
      variety_score?: number;
    };
    party_fit?: {
      members: {
        user_id: number;
        display_name: string;
        average_fit: number;
        matched_stops?: number;
        strong_match_count?: number;
        coverage_status?: 'covered' | 'needs_match' | string;
        best_match?: {
          day_stop_index?: number;
          slot_id?: string;
          slot_label?: string;
          place_id?: number | string;
          name?: string;
          fit?: number;
        } | null;
      }[];
      lowest_average_fit?: number;
      highest_average_fit?: number;
      fairness_score?: number | null;
      coverage_share?: number | null;
      covered_member_count?: number;
      underserved_count?: number;
      underserved_members?: {
        user_id: number;
        display_name: string;
        average_fit: number;
        matched_stops?: number;
        strong_match_count?: number;
        coverage_status?: string;
        best_match?: {
          day_stop_index?: number;
          slot_id?: string;
          slot_label?: string;
          place_id?: number | string;
          name?: string;
          fit?: number;
        } | null;
      }[];
      ready_for_friend_testing?: boolean;
      coverage_plan?: {
        status?: 'ready' | 'needs_member_coverage' | 'watch' | string;
        coverage_share?: number | null;
        covered_member_count?: number;
        underserved_count?: number;
        next_actions?: string[];
      };
      compromise_brief?: GroupCompromiseBrief | null;
      message?: string;
    };
    stops: ItineraryStop[];
  }[];
  price_breakdown?: {
    currency: string;
    party_size: number;
    budget_profile?: string;
    budget_label?: string;
    days?: number;
    nights?: number;
    per_person: {
      places_low?: number;
      places_high?: number;
      local_transit_low?: number;
      local_transit_high?: number;
      total_known_low: number;
      total_known_high: number;
      flight_low?: number | null;
      flight_high?: number | null;
      stay_low?: number | null;
      stay_high?: number | null;
    };
    travelers?: {
      user_id?: number | null;
      display_name: string;
      known_low: number;
      known_high: number;
      components?: {
        type: string;
        label: string;
        low?: number | null;
        high?: number | null;
        status: string;
      }[];
    }[];
    quote_plan?: QuotePlan;
    unknown_cost_components?: string[];
    assumptions: string[];
  };
  booking_plan?: {
    status: string;
    origin?: string;
    travel_dates?: {
      start?: string;
      end?: string;
    };
    duration_alignment?: BookingDurationAlignment;
    missing_inputs?: string[];
    reservation_storage?: {
      status: string;
      message: string;
      supported_types?: string[];
    };
    summary?: BookingSummary;
    planning_burden?: BookingPlanningBurden;
    next_best_actions?: {
      type: string;
      label: string;
      detail?: string;
    }[];
    booking_timeline?: {
      status?: string;
      headline?: string;
      items?: {
        phase?: string;
        label?: string;
        status?: string;
        detail?: string;
        action?: string;
        component_type?: string;
        priority?: number;
        provider?: string | null;
        source_url?: string | null;
        stores_reservation?: boolean;
        reservation_type?: string | null;
      }[];
    };
    booking_action_links?: BookingActionLink[];
    booking_handoff?: BookingHandoff;
    booking_checklist?: BookingChecklist;
    prep_checklist?: BookingPrepChecklist;
    components?: BookingComponent[];
  };
  trip_packet?: TripPacket;
  local_events?: {
    status: string;
    message: string;
    event_plan?: LocalEventPlan;
    summary?: LocalEventSummary;
    date_window?: {
      start?: string;
      end?: string;
      source?: string;
    };
    external_sources?: {
      label: string;
      description: string;
      url?: string | null;
      source_type?: string;
      query?: string | null;
      action?: string;
      reservation_hint?: string;
      priority?: number;
      is_recommended?: boolean;
      recommended_reason?: string;
    }[];
    events?: LocalEventRecommendation[];
  };
  route_readiness?: {
    score: number;
    label: string;
    planned_stop_count: number;
    expected_stop_count: number;
    stop_coverage: number;
    variety_score: number;
    party_score: number;
    party_fairness_score?: number;
    party_coverage_score?: number;
    booking_score: number;
    authenticity_score?: number;
    authenticity_summary?: RouteAuthenticityPacket;
    booking_action_link_count?: number;
    booking_saveable_item_count?: number;
    event_score: number;
    event_social_score?: number;
    event_social_summary?: LocalEventSocialReadiness;
    event_summary?: LocalEventSummary;
    warnings?: string[];
    strengths?: string[];
    booking_summary?: BookingSummary;
  };
  route_authenticity?: RouteAuthenticityPacket;
  scenario_readiness?: ScenarioReadinessSummary;
  route_explanation?: {
    headline?: string;
    reasons?: string[];
    cautions?: string[];
    stats?: {
      stop_count?: number;
      day_count?: number;
      unique_group_count?: number;
      variety_score?: number;
      party_score?: number;
      authenticity_score?: number;
      booking_score?: number;
      event_score?: number;
      route_event_count?: number;
      known_per_person_low?: number;
      known_per_person_high?: number;
    };
  };
  itinerary_story?: {
    headline?: string;
    narrative?: string;
    highlights?: string[];
    planning_steps?: string[];
    badges?: {
      label?: string;
      detail?: string;
      tone?: 'ready' | 'watch' | 'warning' | string;
    }[];
    stats?: {
      local_first_stop_count?: number;
      hidden_gem_stop_count?: number;
      stop_count?: number;
      day_count?: number;
      unique_group_count?: number;
      readiness_score?: number;
      booking_timeline_status?: string;
      budget_profile?: string;
    };
  };
  launch_checklist?: {
    can_start: boolean;
    headline?: string;
    blocking_count?: number;
    action_count?: number;
    warning_count?: number;
    items?: {
      id: string;
      label: string;
      status: 'ready' | 'warning' | 'action_needed' | 'optional' | string;
      detail?: string;
      action?: string;
      blocking?: boolean;
    }[];
  };
  filter_summary?: RecommendationFilterSummary;
  swap_guide?: SwapGuide;
  swap_summary?: {
    swapped_stop_count: number;
    swapped_slots: {
      day: number;
      slot_id: string;
      slot_label: string;
      from_place_id?: number;
      from_name?: string;
      to_place_id?: number;
      to_name?: string;
      swapped_at?: string;
      impact?: ItineraryRecommendation['swap_impact'];
    }[];
  };
};
type ItineraryComparison = {
  scoring_profile: ScoringProfileOption['id'] | string;
  plan?: ItineraryPlan;
  route_readiness?: ItineraryPlan['route_readiness'];
  scenario_readiness?: ScenarioReadinessSummary;
  launch_checklist?: ItineraryPlan['launch_checklist'];
  friend_test_packet?: TripFriendTestPacket | null;
  authenticity_summary?: {
    score?: number;
    label?: string;
    hidden_gem_score?: number;
    hidden_gem_count?: number;
    chain_risk?: number;
  };
  group_fit_summary?: {
    member_count?: number;
    fairness_score?: number | null;
    lowest_fit?: number | null;
    highest_fit?: number | null;
    underserved_count?: number;
    message?: string;
    members?: {
      user_id: number;
      display_name: string;
      average_fit: number;
      matched_days?: number;
    }[];
    underserved_members?: {
      user_id: number;
      display_name: string;
      average_fit: number;
      matched_days?: number;
    }[];
    compromise_brief?: GroupCompromiseBrief | null;
  };
  group_compromise_brief?: GroupCompromiseBrief | null;
  comparison_explanation?: {
    headline?: string;
    tradeoffs?: {
      kind: string;
      label: string;
      value: string;
      tone?: 'positive' | 'neutral' | 'caution' | string;
    }[];
    cautions?: string[];
  };
  comparison_rank?: {
    can_start?: boolean;
    blocking_count?: number;
    action_count?: number;
    trip_readiness_score?: number;
    route_score?: number;
    route_model_confidence_score?: number;
    route_model_status?: string | null;
    route_model_learning_status?: string | null;
    route_model_warning_count?: number;
    route_model_basis_count?: number;
    route_model_stop_coverage?: number;
    route_model_authenticity_score?: number;
    route_model_party_score?: number;
    route_model_booking_score?: number;
    route_model_swap_coverage?: number;
    route_model_learned_guard_status?: string | null;
    swap_safety_score?: number;
    swap_coverage?: number;
    swap_stop_count?: number;
    swap_alternative_count?: number;
    swap_recommended_count?: number;
    swap_low_friction_count?: number;
    swap_route_risk_count?: number;
    swap_cost_caution_count?: number;
    swap_cost_saving_count?: number;
    swap_consensus_upgrade_count?: number;
    swap_party_coverage_status?: string | null;
    swap_party_actionable_member_count?: number;
    swap_party_underserved_member_count?: number;
    swap_party_coverage_score?: number;
    effective_underserved_count?: number;
    learned_requested?: boolean;
    learned_active?: boolean;
    learned_inactive?: boolean;
    learned_reason?: string | null;
    pipeline_health_score?: number;
    pipeline_issue_name?: string | null;
    pipeline_issue_label?: string | null;
    pipeline_issue_status?: string | null;
    pipeline_issue_severity?: number;
    logistics_readiness_score?: number;
    logistics_status?: string | null;
    logistics_missing_input_count?: number;
    logistics_blocking_count?: number;
    logistics_provider_link_count?: number;
    logistics_quote_ready_count?: number;
    logistics_save_ready_count?: number;
    logistics_setup_ready_count?: number;
    logistics_local_transport_status?: string | null;
    logistics_reservation_storage_ready?: boolean;
    booking_handoff_score?: number;
    booking_command_center_status?: string | null;
    booking_command_count?: number;
    booking_command_ready_count?: number;
    booking_command_action_count?: number;
    booking_command_open_link_count?: number;
    booking_command_save_prompt_count?: number;
    booking_command_primary_action_label?: string | null;
    trip_style_fit_score?: number;
    trip_style_fit_status?: string | null;
    trip_style?: string | null;
    trip_style_suggested?: string | null;
    trip_style_duration_fit?: number;
    trip_style_quote_coverage?: number;
    trip_style_event_density?: number;
    trip_style_route_days?: number;
    trip_style_nights?: number;
    travel_quote_status?: string | null;
    travel_quote_required_count?: number;
    travel_quote_ready_count?: number;
    travel_quote_missing_input_count?: number;
    travel_quote_ready_coverage?: number;
    travel_quote_readiness_score?: number;
    planned_stop_count?: number;
    stop_coverage?: number;
    authenticity_score?: number;
    hidden_gem_count?: number;
    chain_risk?: number;
    group_member_count?: number;
    group_fairness_score?: number;
    group_lowest_fit?: number;
    underserved_count?: number;
    friend_member_count?: number;
    friend_testable?: boolean;
    friend_test_status?: string | null;
    friend_test_score?: number | null;
    friend_test_blocker_count?: number;
    friend_test_next_action_count?: number;
    friend_coverage_share?: number;
    friend_average_fit?: number;
    friend_underserved_count?: number;
    friend_covered_member_count?: number;
    friend_rescue_count?: number;
    friend_rescued_members?: string[];
    event_score?: number;
    event_social_score?: number;
    event_actionability_score?: number;
    event_count?: number;
    event_route_match_count?: number;
    event_actionable_count?: number;
    event_reservation_ready_count?: number;
    event_social_anchor_count?: number;
    event_friend_signal_count?: number;
    event_route_anchor_score?: number;
    event_route_anchor_title?: string | null;
    event_route_anchor_reservation_ready?: boolean;
    event_route_anchor_action_url?: string | null;
    event_top_social_title?: string | null;
    booking_score?: number;
    booking_actionable_score?: number;
    booking_action_coverage?: number;
    booking_saveable_coverage?: number;
    booking_action_link_count?: number;
    booking_saveable_item_count?: number;
    party_score?: number;
    planning_burden_score?: number;
    planning_burden_level?: string | null;
    planning_action_needed_count?: number;
    planning_manual_count?: number;
    planning_setup_count?: number;
    planning_provider_action_count?: number;
    warning_count?: number;
    strength_count?: number;
    known_cost_tiebreaker?: number;
  };
  first_stop?: {
    name?: string;
    score?: number;
    diversity_groups?: string[];
  } | null;
  known_per_person?: {
    total_known_low?: number;
    total_known_high?: number;
  };
  warnings?: string[];
  strengths?: string[];
};
type DestinationCandidate = {
  id: string;
  label: string;
  location: Coordinates;
  radius_meters?: number;
  source?: string;
};
type DestinationComparison = ItineraryComparison & {
  destination?: DestinationCandidate;
  destination_id?: string;
  destination_label?: string;
  destination_rank?: ItineraryComparison['comparison_rank'];
  comparison_mode?: 'destination' | string;
  profile_comparisons?: ItineraryComparison[];
};
type ProviderUsageSummary = {
  search_count?: number;
  provider_fetch_count?: number;
  cache_hit_count?: number;
  cache_entry_count?: number;
  saved_fetch_count?: number;
  stripped_constraint_keys?: string[];
};
type LocalEventsPayload = NonNullable<ItineraryPlan['local_events']>;
type BasketComparison = {
  scoring_profile: ScoringProfileOption['id'] | string;
  recommendations?: any[];
  result?: {
    recommendations?: any[];
    preference_insights?: PreferenceInsight[];
    group_fit_summary?: GroupFitSummary | null;
    slate_summary?: SlateSummary | null;
    recommendation_quality?: RecommendationQualitySummary | null;
    scenario_readiness?: ScenarioReadinessSummary | null;
    learned_rerank?: LearnedRerankSummary | null;
    filter_summary?: RecommendationFilterSummary;
    retrieval_context?: RetrievalContext;
    session_context?: SessionContextSummary | null;
    provider_errors?: any[];
  };
  recommendation_quality?: RecommendationQualitySummary | null;
  scenario_readiness?: ScenarioReadinessSummary | null;
  group_fit_summary?: GroupFitSummary | null;
  slate_summary?: SlateSummary | null;
  comparison_rank?: {
    beta_testable?: boolean;
    status?: string;
    returned?: number;
    average_score?: number;
    local_feeling_share?: number;
    hidden_gem_count?: number;
    hidden_gem_share?: number;
    generic_risk_share?: number;
    first_page_local_discovery_count?: number;
    local_discovery_rescue_count?: number;
    average_group_fit?: number | null;
    group_fairness_score?: number | null;
    group_lowest_fit?: number | null;
    party_readiness_score?: number | null;
    underserved_count?: number;
    provider_error_count?: number;
    pipeline_health_score?: number;
    pipeline_issue_name?: string | null;
    pipeline_issue_label?: string | null;
    pipeline_issue_status?: string | null;
    pipeline_issue_severity?: number;
    learned_requested?: boolean;
    learned_active?: boolean;
    learned_inactive?: boolean;
    learned_reason?: string | null;
    warning_count?: number;
    strength_count?: number;
  };
  comparison_explanation?: {
    headline?: string;
    tradeoffs?: {
      kind: string;
      label: string;
      value: string;
      tone?: 'positive' | 'neutral' | 'caution' | string;
    }[];
    cautions?: string[];
  };
  first_pick?: {
    name?: string;
    score?: number;
    diversity_groups?: string[];
    authenticity_label?: string;
  } | null;
  learned_rerank?: LearnedRerankSummary | null;
  warnings?: string[];
  strengths?: string[];
};
type TravelReservation = {
  id: number;
  adventour_session_id?: number | null;
  reservation_type: string;
  title: string;
  provider?: string;
  confirmation_code?: string;
  cost_total?: number | null;
  currency?: string;
  booking_url?: string;
  notes?: string;
  metadata?: Record<string, any>;
};
type ReservationCostImpact = {
  tracked_total: number;
  estimate_add_on_total: number;
  estimate_add_on_types: string[];
};
type ReservationDraft = {
  id?: number;
  reservation_type: string;
  title: string;
  provider: string;
  confirmation_code: string;
  cost_total: string;
  booking_url: string;
  notes: string;
};
type LocalEventDraft = {
  title: string;
  starts_at: string;
  category: string;
  description: string;
  source_url: string;
  reservation_url: string;
};
type LocalEventRecommendation = {
  id: number;
  title: string;
  description?: string;
  category?: string;
  latitude?: number;
  longitude?: number;
  starts_at?: string;
  source_name?: string;
  source_url?: string;
  source?: {
    kind?: string;
    badge?: string;
    source_name?: string | null;
    domain?: string | null;
    trust_score?: number;
    has_source_url?: boolean;
    has_reservation_url?: boolean;
  };
  reservation_url?: string;
  price_low?: number;
  price_high?: number;
  distance_meters?: number;
  score?: number;
  time_fit?: number;
  preference_fit?: number;
  fit_label?: string;
  explanation?: string[];
  event_story?: {
    headline?: string;
    reasons?: string[];
    cautions?: string[];
    confidence?: number;
    source_badge?: string;
    reservation_ready?: boolean;
    social_ready?: boolean;
    distance_label?: string | null;
    metrics?: {
      id: string;
      label: string;
      value?: number;
      display?: string;
    }[];
  };
  event_readiness?: {
    status?: 'ready' | 'needs_confirmation' | 'research' | string;
    headline?: string;
    score?: number;
    source_badge?: string;
    next_action?: string;
    checks?: {
      name: string;
      label: string;
      status: 'pass' | 'warn' | 'watch' | 'fail' | string;
      value?: number;
      target?: string;
      action?: string;
    }[];
  };
  score_components?: {
    authenticity?: number;
    closeness?: number;
    time_fit?: number;
    preference_fit?: number;
    source_quality?: number;
    source_freshness?: number;
    reservation_readiness?: number;
    social_signal?: number;
    event_anchor_score?: number;
    baseline_score?: number;
  };
  social?: {
    interested_count?: number;
    going_count?: number;
    friend_interested_count?: number;
    friend_going_count?: number;
    friend_preview?: {
      user_id: number;
      display_name: string;
      profile_picture?: string | null;
      status: 'interested' | 'going';
    }[];
    friend_candidates?: {
      user_id: number;
      display_name: string;
      profile_picture?: string | null;
      status?: 'interested' | 'going' | null;
    }[];
    social_next_action?: string | null;
    viewer_status?: 'interested' | 'going' | null;
  };
  authenticity_score?: number;
  route_context?: {
    day?: number;
    slot_id?: string;
    slot_label?: string;
    time_window?: string;
    stop_name?: string;
    distance_to_stop_meters?: number | null;
    route_fit?: number;
    fit_label?: string;
    reasons?: string[];
  };
};
type StopLocalEventMatch = {
  id?: number | string;
  title?: string;
  category?: string;
  starts_at?: string;
  fit_label?: string;
  distance_to_stop_meters?: number | null;
  route_fit?: number;
  reasons?: string[];
  source_badge?: string;
  source_url?: string | null;
  reservation_url?: string | null;
  reservation_ready?: boolean;
  readiness_status?: string;
};

const RADIUS_OPTIONS: RadiusOption[] = [
  { id: 'walkable', label: 'Walkable', helper: '10 min', meters: 800 },
  { id: 'nearby', label: 'Nearby', helper: '2 mi', meters: 3200 },
  { id: 'explore', label: 'Explore', helper: '5 mi', meters: 8000 },
  { id: 'wide', label: 'Wide', helper: '10 mi', meters: 16000 },
];

const radiusOptionForMultiplier = (current: RadiusOption, multiplier?: number) => {
  if (!multiplier || multiplier <= 1) {
    return current;
  }
  const targetMeters = current.meters * multiplier;
  return RADIUS_OPTIONS.find((option) => option.meters >= targetMeters)
    || RADIUS_OPTIONS[RADIUS_OPTIONS.length - 1];
};

const PLAN_OPTIONS: PlanOption[] = [
  { id: 'day', label: 'Day trip', helper: '1 day', days: 1 },
  { id: 'weekend', label: 'Weekend', helper: '2 days', days: 2 },
  { id: 'vacation', label: 'Vacation', helper: '3-7 days', days: 3 },
];

const PACE_OPTIONS: PaceOption[] = [
  { id: 'relaxed', label: 'Relaxed', helper: '3 stops/day' },
  { id: 'balanced', label: 'Balanced', helper: '4 stops/day' },
  { id: 'full', label: 'Full', helper: '5 stops/day' },
];

const BUDGET_OPTIONS: BudgetOption[] = [
  { id: 'budget', label: 'Budget', helper: '$' },
  { id: 'flexible', label: 'Flexible', helper: '$$' },
  { id: 'splurge', label: 'Splurge', helper: '$$$' },
];

const LODGING_OPTIONS: LodgingOption[] = [
  { id: 'flexible', label: 'Either', helper: 'best fit' },
  { id: 'hotel', label: 'Hotel', helper: 'simple check-in' },
  { id: 'home_share', label: 'Home-share', helper: 'space/kitchen' },
];

const LOCAL_TRANSPORT_OPTIONS: LocalTransportOption[] = [
  { id: 'auto', label: 'Auto', helper: 'route decides' },
  { id: 'transit', label: 'Transit', helper: 'train/bus' },
  { id: 'rideshare', label: 'Rideshare', helper: 'flexible' },
  { id: 'rental_car', label: 'Rental', helper: 'car-ready' },
];

const DATE_SHORTCUTS = [
  { id: 'today', label: 'Today' },
  { id: 'weekend', label: 'Weekend' },
  { id: 'next_week', label: 'Next week' },
] as const;

const SCORING_PROFILE_OPTIONS: ScoringProfileOption[] = [
  {
    id: 'auto_scout',
    label: 'Auto scout',
    helper: 'Adventour chooses',
    backendProfileId: 'phase1_balanced',
  },
  { id: 'phase1_balanced', label: 'Balanced', helper: 'Taste + local texture' },
  { id: 'authenticity_forward', label: 'Hidden gems', helper: 'Local-first picks' },
  { id: 'group_friendly', label: 'Group fit', helper: 'Blend friends better' },
  { id: 'fresh_discovery', label: 'Fresh finds', helper: 'More variety' },
  { id: 'event_anchor', label: 'Event anchor', helper: 'Timely local happenings' },
  {
    id: 'learned_beta',
    label: 'Learned beta',
    helper: 'Use trained ranker',
    backendProfileId: 'phase1_balanced',
    learnedRerank: true,
  },
];

const scoutStyleForId = (profileId?: string) => (
  SCORING_PROFILE_OPTIONS.find((option) => option.id === profileId)
);

type RemediationAdjustment = NonNullable<ScenarioReadinessSummary['remediation_plan']>[number]['adjustment'];

const remediationAdjustmentLabel = (
  adjustment?: RemediationAdjustment,
) => {
  if (!adjustment) {
    return null;
  }
  if (adjustment.kind === 'rerun_recommendations') {
    const style = scoutStyleForId(adjustment.scoring_profile);
    const pieces = [
      style ? `Try ${style.label} scout` : 'Rerun recommendations',
      adjustment.radius_multiplier && adjustment.radius_multiplier > 1 ? 'widen range' : null,
      adjustment.boost_query_tags?.length
        ? `boost ${adjustment.boost_query_tags.slice(0, 2).map((tag) => tagGroupDisplayLabel(tag) || tag.replace(/_/g, ' ')).join(', ')}`
        : null,
      adjustment.clear_excluded_tag_groups ? 'clear skips' : null,
    ].filter(Boolean);
    return pieces.join(' - ');
  }
  if (adjustment.kind === 'collect_trip_inputs') {
    return adjustment.required_inputs?.length
      ? `Add ${adjustment.required_inputs.slice(0, 3).join(', ')}`
      : 'Add trip details';
  }
  if (adjustment.kind === 'collect_feedback') {
    return 'Collect more swipes, ratings, or reviews';
  }
  if (adjustment.kind === 'scout_local_events') {
    return 'Scout local calendars or add a community event';
  }
  if (adjustment.kind === 'collect_event_social_signal') {
    return 'Ask friends to mark Interested/Going or add a social anchor';
  }
  if (adjustment.kind === 'collect_booking_details') {
    return 'Save provider links, confirmation numbers, and costs';
  }
  return adjustment.reason || null;
};

const remediationButtonLabel = (adjustment?: RemediationAdjustment) => {
  if (!adjustment) {
    return 'Apply repair';
  }
  if (adjustment.kind === 'rerun_recommendations') {
    return 'Apply repair';
  }
  if (adjustment.kind === 'collect_trip_inputs') {
    return 'Add trip details';
  }
  if (adjustment.kind === 'collect_feedback') {
    return 'Keep swiping';
  }
  if (adjustment.kind === 'scout_local_events') {
    return 'Scout events';
  }
  if (adjustment.kind === 'collect_event_social_signal') {
    return 'Add event signal';
  }
  if (adjustment.kind === 'collect_booking_details') {
    return 'Save booking details';
  }
  return 'Review repair';
};

const backendScoringProfileId = (profile: ScoringProfileOption | string): BackendScoringProfileId | string => {
  if (typeof profile === 'string') {
    return profile === 'learned_beta' || profile === 'auto_scout' ? 'phase1_balanced' : profile;
  }
  return profile.backendProfileId || profile.id;
};

const learnedTrainingDataHealthMessage = (health?: LearnedTrainingDataHealth | null) => {
  if (!health) {
    return null;
  }

  const blocking = health.blocking_checks?.[0];
  const watching = health.watch_checks?.[0];
  const status = health.status;
  if (status === 'needs_data') {
    const focus = blocking?.label ? ` Focus: ${blocking.label.toLowerCase()}.` : '';
    return `Training data is too thin for friend testing.${focus}`;
  }
  if (status === 'watch') {
    const focus = watching?.label ? ` Watch: ${watching.label.toLowerCase()}.` : '';
    return `Training data is usable, but needs more representative coverage.${focus}`;
  }
  if (status === 'unknown') {
    return 'Refresh the learned-ranker artifact to show training-data health.';
  }
  return null;
};

const learnedTrainingDataHealthChips = (health?: LearnedTrainingDataHealth | null) => {
  if (!health) {
    return [];
  }

  const counts = health.counts || {};
  const chips: { label: string; style: 'pass' | 'watch' | 'constrained' }[] = [];
  if (health.status === 'ready') {
    chips.push({ label: 'data ready', style: 'pass' });
  } else if (health.status === 'watch') {
    chips.push({ label: 'data watch', style: 'watch' });
  } else if (health.status === 'needs_data') {
    chips.push({ label: 'needs data', style: 'constrained' });
  } else if (health.status === 'unknown') {
    chips.push({ label: 'health unknown', style: 'watch' });
  }

  if (typeof counts.labeled === 'number') {
    chips.push({ label: `${counts.labeled} labels`, style: counts.labeled >= 50 ? 'pass' : 'watch' });
  }
  if (typeof counts.requests === 'number') {
    chips.push({ label: `${counts.requests} requests`, style: counts.requests >= 20 ? 'pass' : 'watch' });
  }
  if (typeof counts.event_friend_signal === 'number' && counts.event_friend_signal > 0) {
    chips.push({ label: `${counts.event_friend_signal} friend-event`, style: 'pass' });
  }

  return chips.slice(0, 4);
};

const learnedRerankStatusMessage = (
  scoringProfile: ScoringProfileOption,
  summary: LearnedRerankSummary | null,
) => {
  if (!scoringProfile.learnedRerank) {
    return null;
  }

  const modelName = summary?.model_type ? ` (${summary.model_type})` : '';
  const gateSummary = summary?.promotion_gate?.summary;
  const runtimeGuard = summary?.runtime_guard;
  const featureCompatibility = summary?.feature_compatibility;
  const healthMessage = learnedTrainingDataHealthMessage(summary?.training_data_health);
  const healthSuffix = healthMessage ? ` ${healthMessage}` : '';
  if (summary?.applied) {
    if (runtimeGuard?.status === 'constrained') {
      return `${runtimeGuard.headline || `Learning ranker active${modelName}, but Adventour guardrails constrained a few picks.`}${healthSuffix}`;
    }
    if (runtimeGuard?.status === 'watch') {
      return `${runtimeGuard.headline || `Learning ranker active${modelName}; Adventour is watching a few borderline picks.`}${healthSuffix}`;
    }
    const activeMessage = summary.override_applied
      ? `Learning ranker active${modelName} with a dev override. ${gateSummary || 'Use this only for smoke testing.'}`
      : runtimeGuard?.headline || `Learning ranker active${modelName}; promotion gate passed.`;
    return `${activeMessage}${healthSuffix}`;
  }

  if (summary?.reason === 'no_model') {
    return 'Learned beta selected, but no model is loaded on the backend yet.';
  }
  if (
    summary?.reason === 'feature_schema_mismatch'
    || summary?.reason === 'feature_schema_version_mismatch'
    || summary?.reason === 'feature_names_missing'
  ) {
    const missingCount = featureCompatibility?.missing_features?.length || 0;
    const missingText = missingCount
      ? ` Missing ${missingCount} current signal${missingCount === 1 ? '' : 's'}.`
      : '';
    return `${featureCompatibility?.message || 'Learned beta is blocked because this model was trained with an older Adventour feature map.'}${missingText} Retrain the ranker before friend testing.`;
  }
  if (summary?.reason === 'promotion_gate_missing') {
    return `${gateSummary || 'Learned beta is blocked until the model is evaluated against Adventour quality gates.'}${healthSuffix}`;
  }
  if (summary?.reason?.startsWith('promotion_gate_')) {
    return `${gateSummary || 'Learned beta is blocked because the model did not pass Adventour quality gates.'}${healthSuffix}`;
  }
  if (summary?.reason === 'training_data_needs_data') {
    return healthMessage || 'Learned beta needs more representative training data before friend testing.';
  }
  if (summary?.reason === 'training_data_unknown') {
    return healthMessage || 'Refresh the learned-ranker artifact so Adventour can inspect training-data health.';
  }

  return `Learned beta will activate only after the backend has a promoted model loaded.${healthSuffix}`;
};

const learnedRerankNeedsAttention = (summary: LearnedRerankSummary | null) => (
  Boolean(summary && !summary.applied && summary.reason && summary.reason !== 'not_enabled')
);

const learnedRerankBlockedLabel = (summary: LearnedRerankSummary | null) => {
  if (!summary || summary.applied) {
    return null;
  }
  if (summary.reason === 'no_model') {
    return 'Model not loaded';
  }
  if (
    summary.reason === 'feature_schema_mismatch'
    || summary.reason === 'feature_schema_version_mismatch'
    || summary.reason === 'feature_names_missing'
  ) {
    return 'Retrain needed';
  }
  if (summary.reason === 'promotion_gate_missing') {
    return 'Needs evaluation';
  }
  if (summary.reason?.startsWith('promotion_gate_')) {
    return 'Gate blocked';
  }
  if (summary.reason === 'training_data_needs_data') {
    return 'Needs data';
  }
  if (summary.reason === 'training_data_unknown') {
    return 'Refresh model';
  }
  return 'Learning paused';
};

const learnedRankerReadyForAutoScout = (summary: LearnedRerankSummary | null) => (
  Boolean(
    summary?.ready
    || summary?.applied
    || (
      summary?.feature_compatibility?.status === 'pass'
      && summary?.promotion_gate?.status === 'pass'
      && summary?.promotion_gate?.can_promote === true
    )
  )
);

const learnedRankerAutoScoutSkipMessage = (
  summary: LearnedRerankSummary | null,
  loading: boolean,
) => {
  if (loading && !summary) {
    return 'Auto scout is checking whether Learned beta can join this comparison.';
  }

  const label = learnedRerankBlockedLabel(summary);
  if (label) {
    return `Auto scout will skip Learned beta for now: ${label.toLowerCase()}.`;
  }

  return 'Auto scout will skip Learned beta until the trained ranker is loaded, current, and promotion-ready.';
};

const providerUsageLabel = (usage?: ProviderUsageSummary | null) => {
  if (!usage) {
    return null;
  }
  const fetches = usage.provider_fetch_count ?? 0;
  const saved = usage.saved_fetch_count ?? 0;
  if (fetches <= 0 && saved <= 0) {
    return null;
  }
  const fetchLabel = `${fetches} provider fetch${fetches === 1 ? '' : 'es'}`;
  const savedLabel = saved > 0
    ? `, ${saved} reuse${saved === 1 ? '' : 's'} saved`
    : '';
  return `${fetchLabel}${savedLabel}`;
};

const BACKEND_SCORING_PROFILE_OPTIONS = SCORING_PROFILE_OPTIONS.filter((option) => (
  !option.learnedRerank && option.id !== 'auto_scout'
));
const LEARNED_SCORING_PROFILE = SCORING_PROFILE_OPTIONS.find((option) => option.learnedRerank);
const AUTO_SCOUT_COMPARISON_OPTIONS = SCORING_PROFILE_OPTIONS.filter((option) => (
  option.id !== 'auto_scout'
));

const PRICE_LEVEL_ESTIMATES: Record<number, [number, number]> = {
  0: [0, 10],
  1: [10, 20],
  2: [20, 45],
  3: [45, 85],
  4: [85, 150],
};
const PARTY_STRONG_FIT_THRESHOLD = 0.65;

const quotePlanMessage = (
  status: string,
  labels: string[],
  missingInputs: string[],
) => {
  if (status === 'local_estimate_only') {
    return 'Adventour is only tracking local place and transport estimates for this route.';
  }
  const readableLabels = labels.join(', ');
  if (status === 'ready_to_quote') {
    return `${readableLabels} still need live prices, and provider links are ready to open.`;
  }
  if (missingInputs.length) {
    return `${readableLabels} still need live prices; add ${missingInputs.slice(0, 3).map((item) => item.replace(/_/g, ' ')).join(', ')} to unlock reliable quotes.`;
  }
  return `${readableLabels} still need live provider quotes.`;
};

const quotePlanForItineraryPlan = (
  plan: ItineraryPlan,
  perPersonOverride?: NonNullable<ItineraryPlan['price_breakdown']>['per_person'],
): QuotePlan => {
  const perPerson = perPersonOverride || plan.price_breakdown?.per_person || {};
  const currentQuotePlan = plan.price_breakdown?.quote_plan || plan.trip_packet?.quote_plan || plan.trip_packet?.cost_confidence?.quote_plan;
  const currentItemsByType = new Map((currentQuotePlan?.items || []).map((item) => [item.type, item]));
  const componentsByType = new Map((plan.booking_plan?.components || []).map((component) => [component.type, component]));
  const linksByType = new Map((plan.booking_plan?.booking_action_links || []).map((link) => [link.component_type, link]));
  const items = [
    { type: 'flight', label: 'Flight or train', lowKey: 'flight_low', highKey: 'flight_high' },
    { type: 'stay', label: 'Stay', lowKey: 'stay_low', highKey: 'stay_high' },
  ].map(({ type, label, lowKey, highKey }) => {
    const component = componentsByType.get(type);
    const currentItem = currentItemsByType.get(type);
    const link = linksByType.get(type);
    const status = component?.status || currentItem?.status || 'not_configured';
    let quoteRequired = (perPerson as Record<string, number | null | undefined>)[lowKey] == null
      || (perPerson as Record<string, number | null | undefined>)[highKey] == null;
    if (['optional_for_day_trip', 'not_needed_for_day_trip'].includes(status)) {
      quoteRequired = false;
    }
    if (!quoteRequired && !component && !currentItem) {
      return null;
    }
    const missingInputs = component?.missing_inputs || currentItem?.missing_inputs || [];
    const providerOptions = (component?.provider_options || currentItem?.provider_options || []).slice(0, 3);
    const primaryUrl = link?.url || currentItem?.primary_url || providerOptions.find((option) => option.url)?.url || null;
    return {
      type,
      label,
      status,
      quote_required: quoteRequired,
      quote_status: quoteRequired && primaryUrl && !missingInputs.length
        ? 'ready_to_quote'
        : quoteRequired && missingInputs.length
          ? 'needs_details'
          : quoteRequired
            ? 'manual'
            : 'not_needed',
      missing_inputs: missingInputs,
      search_hint: component?.search_hint || currentItem?.search_hint || null,
      provider_options: providerOptions,
      primary_provider_label: link?.provider_label || currentItem?.primary_provider_label || providerOptions[0]?.label || null,
      primary_url: primaryUrl,
      next_steps: (component?.next_steps || currentItem?.next_steps || []).slice(0, 3),
    };
  }).filter(Boolean) as NonNullable<QuotePlan['items']>;
  const requiredItems = items.filter((item) => item.quote_required);
  const readyItems = requiredItems.filter((item) => item.quote_status === 'ready_to_quote');
  const missingInputs = Array.from(new Set(requiredItems.flatMap((item) => item.missing_inputs || []))).sort();
  const status = !requiredItems.length
    ? 'local_estimate_only'
    : readyItems.length === requiredItems.length
      ? 'ready_to_quote'
      : missingInputs.length
        ? 'needs_details'
        : 'manual';

  return {
    ...(currentQuotePlan || {}),
    status,
    headline: status === 'ready_to_quote'
      ? 'Known local costs are estimated; travel quotes are ready to compare.'
      : status === 'needs_details'
        ? 'Add trip basics before Adventour can prepare reliable travel quotes.'
        : currentQuotePlan?.headline || 'Travel quote readiness is tracked separately from local estimates.',
    items,
    required_count: requiredItems.length,
    ready_count: readyItems.length,
    missing_inputs: missingInputs,
    message: quotePlanMessage(status, requiredItems.map((item) => item.label || item.type || 'Travel').filter(Boolean), missingInputs),
  };
};

const TYPE_DIVERSITY_GROUPS: Record<string, string[]> = {
  food_drink: [
    'restaurant',
    'lunch_restaurant',
    'breakfast_restaurant',
    'brunch_restaurant',
    'mexican_restaurant',
    'seafood_restaurant',
    'sandwich_shop',
    'cafe',
    'coffee_shop',
    'bakery',
  ],
  arts_culture: [
    'museum',
    'art_gallery',
    'historical_landmark',
    'performing_arts_theater',
    'concert_hall',
    'comedy_club',
  ],
  outdoors: ['park', 'garden', 'zoo', 'aquarium', 'hiking_area'],
  shopping_market: ['market', 'book_store', 'clothing_store', 'shopping_mall'],
  nightlife: ['bar', 'night_club', 'concert_hall', 'comedy_club'],
};

const EVENT_CATEGORY_SLOT_HINTS: Record<string, string[]> = {
  market: ['late_morning_discovery', 'afternoon_gem'],
  makers: ['late_morning_discovery', 'afternoon_gem'],
  popup: ['lunch', 'afternoon_gem', 'evening_finish'],
  food: ['lunch', 'evening_finish'],
  music: ['evening_finish'],
  concert: ['evening_finish'],
  art: ['late_morning_discovery', 'afternoon_gem'],
  gallery: ['late_morning_discovery', 'afternoon_gem'],
  theater: ['evening_finish'],
  comedy: ['evening_finish'],
  outdoor: ['late_morning_discovery', 'afternoon_gem'],
  community: ['late_morning_discovery', 'afternoon_gem', 'evening_finish'],
};

const EVENT_HOUR_SLOT_HINTS: { start: number; end: number; slotIds: string[] }[] = [
  { start: 6, end: 11, slotIds: ['morning_anchor', 'late_morning_discovery'] },
  { start: 11, end: 14, slotIds: ['lunch'] },
  { start: 14, end: 17, slotIds: ['afternoon_gem'] },
  { start: 17, end: 24, slotIds: ['evening_finish'] },
  { start: 0, end: 3, slotIds: ['evening_finish'] },
];

const clampScore = (value: number, minimum = 0, maximum = 1) =>
  Math.max(minimum, Math.min(maximum, value));

const parseTripDateValue = (value: string) => {
  const match = value.trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) {
    return null;
  }
  const [, year, month, day] = match;
  const parsedYear = Number(year);
  const parsedMonth = Number(month);
  const parsedDay = Number(day);
  const timestamp = Date.UTC(parsedYear, parsedMonth - 1, parsedDay);
  if (!Number.isFinite(timestamp)) {
    return null;
  }
  const parsed = new Date(timestamp);
  if (
    parsed.getUTCFullYear() !== parsedYear
    || parsed.getUTCMonth() !== parsedMonth - 1
    || parsed.getUTCDate() !== parsedDay
  ) {
    return null;
  }
  return timestamp;
};

const tripDayCountFromDates = (fallbackDays: number, start: string, end: string) => {
  const startTime = parseTripDateValue(start);
  const endTime = parseTripDateValue(end);
  if (startTime === null || endTime === null || endTime < startTime) {
    return fallbackDays;
  }
  const dayMs = 24 * 60 * 60 * 1000;
  return Math.max(1, Math.min(MAX_ITINERARY_DAYS, Math.round((endTime - startTime) / dayMs) + 1));
};

const planOptionForDayCount = (days: number) => {
  if (days <= 1) {
    return PLAN_OPTIONS[0];
  }
  if (days <= 3) {
    return PLAN_OPTIONS[1];
  }
  return PLAN_OPTIONS[2];
};

const formatTripDateValue = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const addDays = (date: Date, days: number) => {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
};

const addMonths = (date: Date, months: number) => {
  const next = new Date(date.getFullYear(), date.getMonth() + months, 1);
  next.setHours(0, 0, 0, 0);
  return next;
};

const calendarMonthLabel = (date: Date) =>
  date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

const calendarDaysForMonth = (monthDate: Date) => {
  const first = new Date(monthDate.getFullYear(), monthDate.getMonth(), 1);
  const firstWeekday = first.getDay();
  const daysInMonth = new Date(monthDate.getFullYear(), monthDate.getMonth() + 1, 0).getDate();
  const blanks = Array.from({ length: firstWeekday }, () => null);
  const days = Array.from({ length: daysInMonth }, (_, index) => (
    new Date(monthDate.getFullYear(), monthDate.getMonth(), index + 1)
  ));
  return [...blanks, ...days];
};

const tripDateValidationMessage = (start: string, end: string) => {
  const trimmedStart = start.trim();
  const trimmedEnd = end.trim();
  if (!trimmedStart && !trimmedEnd) {
    return null;
  }
  const startTime = trimmedStart ? parseTripDateValue(trimmedStart) : null;
  const endTime = trimmedEnd ? parseTripDateValue(trimmedEnd) : null;
  if (trimmedStart && startTime === null) {
    return 'Start date should look like 2026-07-10.';
  }
  if (trimmedEnd && endTime === null) {
    return 'End date should look like 2026-07-12.';
  }
  if ((trimmedStart && !trimmedEnd) || (!trimmedStart && trimmedEnd)) {
    return 'Add both dates so flights, stays, and events line up.';
  }
  if (startTime !== null && endTime !== null && endTime < startTime) {
    return 'End date should be the same day or after the start date.';
  }
  return null;
};

const shortcutTripRange = (shortcutId: (typeof DATE_SHORTCUTS)[number]['id']) => {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  if (shortcutId === 'today') {
    return { start: formatTripDateValue(today), end: formatTripDateValue(today) };
  }

  if (shortcutId === 'weekend') {
    const dayOfWeek = today.getDay();
    const daysUntilFriday = (5 - dayOfWeek + 7) % 7;
    const friday = addDays(today, daysUntilFriday);
    const sunday = addDays(friday, 2);
    return { start: formatTripDateValue(friday), end: formatTripDateValue(sunday) };
  }

  const nextWeekStart = addDays(today, 7);
  return { start: formatTripDateValue(nextWeekStart), end: formatTripDateValue(addDays(nextWeekStart, 4)) };
};

const haversineMeters = (start: Coordinates, end: Coordinates) => {
  const radius = 6371000;
  const toRadians = (value: number) => value * Math.PI / 180;
  const phi1 = toRadians(start.latitude);
  const phi2 = toRadians(end.latitude);
  const deltaPhi = toRadians(end.latitude - start.latitude);
  const deltaLambda = toRadians(end.longitude - start.longitude);
  const a = (
    Math.sin(deltaPhi / 2) ** 2
    + Math.cos(phi1) * Math.cos(phi2) * Math.sin(deltaLambda / 2) ** 2
  );
  return radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
};

const diversityGroupsForItineraryRecommendation = (recommendation?: ItineraryRecommendation) => {
  if (!recommendation) {
    return ['other'];
  }
  if (recommendation.diversity_groups?.length) {
    return recommendation.diversity_groups;
  }
  const types = recommendation.display?.types || [];
  const groups = Object.entries(TYPE_DIVERSITY_GROUPS)
    .filter(([, groupTypes]) => types.some((type) => groupTypes.includes(type)))
    .map(([group]) => group);
  return groups.length ? groups : ['other'];
};

const itineraryRecommendationName = (item?: ItineraryRecommendation) =>
  item?.name || item?.display?.name || 'Adventour pick';

const friendHistorySignalForItineraryRecommendation = (recommendation?: ItineraryRecommendation) => {
  const friendHistoryFit = recommendation?.components?.friend_history_fit || 0;
  const likedBy = recommendation?.history?.friend_liked_by || [];
  const rejectedBy = recommendation?.history?.friend_rejected_by || [];

  if (friendHistoryFit >= 0.25 && likedBy.length) {
    return {
      tone: 'positive' as const,
      label: likedBy.length === 1 ? `Liked by ${likedBy[0]}` : `Liked by ${likedBy[0]} +${likedBy.length - 1}`,
    };
  }

  if (friendHistoryFit <= -0.15 && rejectedBy.length) {
    return {
      tone: 'caution' as const,
      label: rejectedBy.length === 1 ? `Passed by ${rejectedBy[0]}` : `Passed by ${rejectedBy[0]} +${rejectedBy.length - 1}`,
    };
  }

  return null;
};

const routeBalanceForItineraryStops = (stops: ItineraryStop[]) => {
  const groupCounts = stops.reduce<Record<string, number>>((counts, stop) => {
    diversityGroupsForItineraryRecommendation(stop.recommendation).forEach((group) => {
      counts[group] = (counts[group] || 0) + 1;
    });
    return counts;
  }, {});

  return {
    unique_groups: Object.keys(groupCounts).sort(),
    group_counts: groupCounts,
    variety_score: Number((Object.keys(groupCounts).length / Math.max(1, stops.length)).toFixed(3)),
  };
};

const coordinatesForItineraryRecommendation = (recommendation?: ItineraryRecommendation): Coordinates | null => {
  const latitude = recommendation?.latitude ?? recommendation?.display?.latitude;
  const longitude = recommendation?.longitude ?? recommendation?.display?.longitude;
  if (typeof latitude !== 'number' || typeof longitude !== 'number') {
    return null;
  }
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }
  return { latitude, longitude };
};

const coordinatesForLocalEvent = (event?: LocalEventRecommendation): Coordinates | null => {
  if (typeof event?.latitude !== 'number' || typeof event.longitude !== 'number') {
    return null;
  }
  if (!Number.isFinite(event.latitude) || !Number.isFinite(event.longitude)) {
    return null;
  }
  return { latitude: event.latitude, longitude: event.longitude };
};

const eventCategorySlotHints = (event: LocalEventRecommendation) => {
  const category = (event.category || '').trim().toLowerCase();
  const hints = new Set<string>();
  Object.entries(EVENT_CATEGORY_SLOT_HINTS).forEach(([key, slotIds]) => {
    if (category === key || (key && category.includes(key))) {
      slotIds.forEach((slotId) => hints.add(slotId));
    }
  });
  return hints;
};

const eventTimeSlotHints = (event: LocalEventRecommendation) => {
  if (!event.starts_at) {
    return new Set<string>();
  }
  const parsed = new Date(event.starts_at);
  if (Number.isNaN(parsed.getTime())) {
    return new Set<string>();
  }
  const hour = parsed.getHours();
  const hints = new Set<string>();
  EVENT_HOUR_SLOT_HINTS.forEach((window) => {
    if (hour >= window.start && hour < window.end) {
      window.slotIds.forEach((slotId) => hints.add(slotId));
    }
  });
  return hints;
};

const eventRouteContextForPlan = (event: LocalEventRecommendation, plan: ItineraryPlan) => {
  const eventCoordinates = coordinatesForLocalEvent(event);
  const categoryHints = eventCategorySlotHints(event);
  const timeHints = eventTimeSlotHints(event);
  const matches: NonNullable<LocalEventRecommendation['route_context']>[] = [];

  plan.days.forEach((day) => {
    day.stops.forEach((stop) => {
      const stopCoordinates = coordinatesForItineraryRecommendation(stop.recommendation);
      const distance = eventCoordinates && stopCoordinates
        ? haversineMeters(eventCoordinates, stopCoordinates)
        : null;
      const distanceFit = distance === null ? 0.45 : clampScore(1 - (distance / 1800));
      const categoryMatch = categoryHints.has(stop.slot_id);
      const slotTimeMatch = timeHints.has(stop.slot_id);
      const eventScore = event.score || 0;
      const routeFit = (
        distanceFit * 0.42
        + (categoryMatch ? 0.24 : 0)
        + (slotTimeMatch ? 0.18 : 0)
        + eventScore * 0.16
      );

      if (distance !== null && distance > 2500 && !categoryMatch && !slotTimeMatch) {
        return;
      }

      const reasons: string[] = [];
      if (distance !== null) {
        if (distance <= 700) {
          reasons.push(`${Math.round(distance)}m from ${itineraryRecommendationName(stop.recommendation)}`);
        } else if (distance <= 1600) {
          reasons.push(`Near ${itineraryRecommendationName(stop.recommendation)}`);
        }
      }
      if (categoryMatch) {
        reasons.push('Event category fits this route slot');
      }
      if (slotTimeMatch) {
        reasons.push('Timing lines up with the route');
      }
      if (!reasons.length) {
        reasons.push('Adds a local happening near the route');
      }

      const fitLabel = distance !== null && distance <= 700
        ? `Near ${stop.label}`
        : categoryMatch || slotTimeMatch
          ? `Pairs with ${stop.label}`
          : `Route idea near ${stop.label}`;

      matches.push({
        day: day.day,
        slot_id: stop.slot_id,
        slot_label: stop.label,
        time_window: stop.time_window,
        stop_name: itineraryRecommendationName(stop.recommendation),
        distance_to_stop_meters: distance === null ? null : Math.round(distance),
        route_fit: Number(routeFit.toFixed(3)),
        fit_label: fitLabel,
        reasons: reasons.slice(0, 3),
      });
    });
  });

  if (!matches.length) {
    return null;
  }

  return matches.sort((a, b) => (b.route_fit || 0) - (a.route_fit || 0))[0];
};

const groupCompromiseBriefForMembers = (
  members: {
    user_id?: number | string;
    display_name?: string;
    average_fit?: number | null;
    coverage_status?: string;
  }[],
  underservedMembers: {
    user_id?: number | string;
    display_name?: string;
    average_fit?: number | null;
  }[],
  fairnessScore?: number | null,
  coverageShare?: number | null,
): GroupCompromiseBrief => {
  if (!members.length) {
    return {
      status: 'unknown',
      headline: 'Party fit needs preference data.',
      message: 'Adventour needs a few taste signals before it can explain who this route serves best.',
      next_action: 'Have each traveler swipe on a few places before trusting a group route.',
      balance_chips: [{ label: 'Coverage', value: 'learning', tone: 'neutral' }],
    };
  }

  const ordered = [...members].sort((a, b) => (a.average_fit || 0) - (b.average_fit || 0));
  const mostCompromised = ordered[0];
  const dominant = ordered[ordered.length - 1];
  const fitGap = Math.max(0, (dominant.average_fit || 0) - (mostCompromised.average_fit || 0));
  const coverage = coverageShare ?? 0;
  const underservedNames = underservedMembers.slice(0, 2).map((member) => member.display_name || 'Traveler').join(', ');
  let status: GroupCompromiseBrief['status'] = 'watch';
  let headline = 'Good blend, worth checking.';
  let message = 'The route looks usable, but Adventour should keep watching for stronger personal coverage.';
  let nextAction = 'Review the weakest traveler fit before starting.';

  if (members.length === 1) {
    status = 'solo';
    headline = `Built around ${dominant.display_name || 'this traveler'}.`;
    message = 'This Adventour is personalized for one traveler right now.';
    nextAction = 'Add friends to blend preferences before planning a group route.';
  } else if (underservedMembers.length) {
    status = 'needs_coverage';
    headline = `${underservedNames || 'Someone'} needs a stronger match.`;
    message = 'The route has a favorite, but at least one traveler does not have a strong personal stop yet.';
    nextAction = `Swap in a stop that better matches ${underservedNames || 'the underserved traveler'}.`;
  } else if (coverage >= 1 && (fairnessScore || 0) >= 0.85 && fitGap <= 0.18) {
    status = 'balanced';
    headline = 'Balanced for the whole party.';
    message = 'Every traveler has a strong stop and the route is not leaning too hard toward one person.';
    nextAction = 'This is a strong route to start or share with friends.';
  } else if (coverage >= 1) {
    status = 'covered_but_uneven';
    headline = `${dominant.display_name || 'One traveler'} may love this most.`;
    message = 'Everyone has a strong stop, but one traveler is carrying more of the route fit.';
    nextAction = `Use a swap if you want ${mostCompromised.display_name || 'everyone'} to feel more centered.`;
  } else if (fairnessScore !== null && fairnessScore !== undefined && fairnessScore < 0.7) {
    status = 'uneven';
    headline = 'This route needs a fairer blend.';
    message = `${dominant.display_name || 'One traveler'} is better served than ${mostCompromised.display_name || 'another traveler'}.`;
    nextAction = 'Try a different scout style or swap the weakest match before sharing.';
  }

  return {
    status,
    headline,
    message,
    dominant_member: dominant,
    most_compromised_member: mostCompromised,
    fit_gap: Number(fitGap.toFixed(3)),
    coverage_share: Number(coverage.toFixed(3)),
    fairness_score: fairnessScore ?? null,
    next_action: nextAction,
    balance_chips: [
      { label: 'Coverage', value: `${Math.round(coverage * 100)}%`, tone: coverage >= 1 ? 'positive' : 'caution' },
      { label: 'Gap', value: `${Math.round(fitGap * 100)} pts`, tone: fitGap <= 0.18 ? 'positive' : 'caution' },
      { label: 'Needs match', value: String(underservedMembers.length), tone: underservedMembers.length ? 'caution' : 'positive' },
    ],
  };
};

const partyFitForItineraryStops = (stops: ItineraryStop[]) => {
  const totals = new Map<number, {
    display_name: string;
    total: number;
    count: number;
    strong_match_count: number;
    best_match: NonNullable<NonNullable<ItineraryPlan['days'][number]['party_fit']>['members'][number]['best_match']> | null;
  }>();

  stops.forEach((stop, index) => {
    (stop.recommendation.member_fit || []).forEach((member) => {
      const current = totals.get(member.user_id) || {
        display_name: member.display_name || 'Traveler',
        total: 0,
        count: 0,
        strong_match_count: 0,
        best_match: null,
      };
      const bestMatch = !current.best_match || member.fit > (current.best_match.fit || 0)
        ? {
          day_stop_index: index + 1,
          slot_id: stop.slot_id,
          slot_label: stop.label,
          place_id: stop.recommendation.place_id,
          name: stop.recommendation.name || stop.recommendation.display?.name || stop.label,
          fit: Number(member.fit.toFixed(3)),
        }
        : current.best_match;
      totals.set(member.user_id, {
        display_name: current.display_name,
        total: current.total + member.fit,
        count: current.count + 1,
        strong_match_count: current.strong_match_count + (member.fit >= PARTY_STRONG_FIT_THRESHOLD ? 1 : 0),
        best_match: bestMatch,
      });
    });
  });

  const members = Array.from(totals.entries())
    .map(([user_id, value]) => {
      const strongMatchCount = value.strong_match_count;
      return {
        user_id,
        display_name: value.display_name,
        average_fit: Number((value.total / Math.max(1, value.count)).toFixed(3)),
        matched_stops: value.count,
        strong_match_count: strongMatchCount,
        coverage_status: strongMatchCount > 0 ? 'covered' : 'needs_match',
        best_match: value.best_match,
      };
    })
    .sort((a, b) => a.user_id - b.user_id);

  if (!members.length) {
    return {
      members: [],
      fairness_score: null,
      message: 'Party fit will appear after Adventour has preference data for this route.',
      coverage_share: null,
      covered_member_count: 0,
      underserved_count: 0,
      underserved_members: [],
      ready_for_friend_testing: false,
      compromise_brief: groupCompromiseBriefForMembers([], [], null, null),
    };
  }

  const fitValues = members.map((member) => member.average_fit);
  const lowest = Math.min(...fitValues);
  const highest = Math.max(...fitValues);
  const fairness_score = Number(Math.max(0, 1 - (highest - lowest)).toFixed(3));
  const coveredMembers = members.filter((member) => member.coverage_status === 'covered');
  const underservedMembers = members.filter((member) => member.coverage_status !== 'covered');
  const coverageShare = coveredMembers.length / Math.max(1, members.length);
  let message = 'One traveler may love this route more than the others; use swaps to rebalance it.';
  if (members.length === 1) {
    message = `Built around ${members[0].display_name}'s Adventour taste.`;
  } else if (coverageShare >= 1 && fairness_score >= 0.85) {
    message = 'Every traveler has a strong route stop and party balance is high.';
  } else if (coverageShare >= 1) {
    message = 'Every traveler has at least one strong route stop.';
  } else if (underservedMembers.length) {
    message = `${underservedMembers.slice(0, 2).map((member) => member.display_name).join(', ')} may need a stronger route stop; use swaps to rebalance.`;
  } else if (fairness_score >= 0.85) {
    message = 'Strongly balanced for this travel party.';
  } else if (fairness_score >= 0.7) {
    message = 'Good party balance with a few stronger personal matches.';
  }

  return {
    members,
    lowest_average_fit: lowest,
    highest_average_fit: highest,
    fairness_score,
    coverage_share: Number(coverageShare.toFixed(3)),
    covered_member_count: coveredMembers.length,
    underserved_count: underservedMembers.length,
    underserved_members: underservedMembers,
    ready_for_friend_testing: coverageShare >= 1 && fairness_score >= 0.7,
    coverage_plan: {
      status: coverageShare >= 1 && fairness_score >= 0.7
        ? 'ready'
        : underservedMembers.length
          ? 'needs_member_coverage'
          : 'watch',
      coverage_share: Number(coverageShare.toFixed(3)),
      covered_member_count: coveredMembers.length,
      underserved_count: underservedMembers.length,
      next_actions: coverageShare >= 1 && fairness_score >= 0.7
        ? ['Keep this route or start the Adventour with the group.']
        : underservedMembers.length
          ? [`Use group-friendly scout style or swap in a stronger stop for ${underservedMembers.slice(0, 2).map((member) => member.display_name).join(', ')}.`]
          : ['Review group fit before sharing this route.'],
    },
    compromise_brief: groupCompromiseBriefForMembers(
      members,
      underservedMembers,
      fairness_score,
      coverageShare,
    ),
    message,
  };
};

const coverageRescueForItineraryRecommendation = (recommendation?: ItineraryRecommendation) => {
  const ranking = recommendation?.ranking;
  if (!ranking?.party_coverage_rescue) {
    return null;
  }

  return {
    member: ranking.rescued_member || 'a traveler',
    fit: typeof ranking.rescued_member_fit === 'number'
      ? Number(ranking.rescued_member_fit.toFixed(3))
      : null,
    replaced_pick: ranking.replaced_pick,
    reason: ranking.rescue_reason,
    score_gap: ranking.score_gap,
  };
};

const partyFitSummaryForItineraryRecommendation = (
  recommendation?: ItineraryRecommendation,
): ItineraryStop['party_fit_summary'] => {
  const coverageRescue = coverageRescueForItineraryRecommendation(recommendation);
  const memberFit = [...(recommendation?.member_fit || [])]
    .filter((member) => typeof member.fit === 'number')
    .sort((a, b) => b.fit - a.fit);

  if (!memberFit.length) {
    return {
      headline: 'Preference fit will improve as Adventour learns this travel party.',
      top_members: [],
      weak_members: [],
      average_fit: null,
      lowest_fit: null,
      highest_fit: null,
      coverage_rescue: coverageRescue,
    };
  }

  const topMembers = memberFit.filter((member) => member.fit >= 0.65).slice(0, 2);
  const weakMembers = memberFit.filter((member) => member.fit < 0.45).slice(0, 2);
  const averageFit = memberFit.reduce((total, member) => total + member.fit, 0) / memberFit.length;

  const headline = coverageRescue
    ? `Made room for ${coverageRescue.member}${typeof coverageRescue.fit === 'number' ? ` at ${Math.round(coverageRescue.fit * 100)}% fit.` : '.'}`
    : memberFit.length === 1
      ? `Best signal for ${memberFit[0].display_name || 'Traveler'} at ${Math.round(memberFit[0].fit * 100)}% fit.`
      : weakMembers.length
        ? `Mixed party fit; ${weakMembers.map((member) => member.display_name || 'Traveler').join(', ')} may prefer a swap.`
        : topMembers.length
          ? `Strong group signal, especially for ${topMembers.map((member) => member.display_name || 'Traveler').join(', ')}.`
          : 'Moderate group fit; this stop keeps the route balanced.';

  return {
    headline,
    top_members: topMembers.map((member) => ({
      user_id: member.user_id,
      display_name: member.display_name || 'Traveler',
      fit: Number(member.fit.toFixed(3)),
    })),
    weak_members: weakMembers.map((member) => ({
      user_id: member.user_id,
      display_name: member.display_name || 'Traveler',
      fit: Number(member.fit.toFixed(3)),
    })),
    average_fit: Number(averageFit.toFixed(3)),
    lowest_fit: Number(memberFit[memberFit.length - 1].fit.toFixed(3)),
    highest_fit: Number(memberFit[0].fit.toFixed(3)),
    coverage_rescue: coverageRescue,
  };
};

const whyThisStopForItineraryRecommendation = (
  stop: ItineraryStop,
  recommendation?: ItineraryRecommendation,
): ItineraryStop['why_this_stop'] => {
  const components = recommendation?.components || {};
  const evidence = recommendation?.authenticity_evidence || {};
  const coverageRescue = coverageRescueForItineraryRecommendation(recommendation);
  const reasons: string[] = [];
  const cautions: string[] = [];
  const groupLabels = diversityGroupsForItineraryRecommendation(recommendation)
    .slice(0, 2)
    .map((group) => group.replace(/_/g, ' '));

  if (coverageRescue) {
    reasons.push(
      `Adventour made room for this stop because it gives ${coverageRescue.member} ${
        typeof coverageRescue.fit === 'number'
          ? `a ${Math.round(coverageRescue.fit * 100)}% personal match.`
          : 'a strong personal match.'
      }`,
    );
  }

  if (groupLabels.length) {
    reasons.push(`Fits the ${stop.label.toLowerCase()} stop with ${groupLabels.join(' and ')} route texture.`);
  }

  if ((evidence.hidden_gem_score || 0) >= 0.7) {
    const detail = evidence.reasons?.slice(0, 2).join(', ');
    reasons.push(`Hidden-gem signal is strong${detail ? `: ${detail}.` : '.'}`);
  } else if ((components.authenticity || evidence.score || 0) >= 0.7) {
    reasons.push(`Local-authentic signal is strong${evidence.label ? ` (${evidence.label})` : ''}.`);
  } else if (evidence.label) {
    reasons.push(`Local signal reads as ${evidence.label.toLowerCase()}.`);
  }

  if ((components.group_member_count || 1) > 1 && typeof components.group_min_fit === 'number') {
    if (components.group_min_fit >= 0.55) {
      reasons.push(`Keeps the travel party above ${Math.round(components.group_min_fit * 100)}% minimum fit.`);
    } else {
      cautions.push(`Party fit is mixed; lowest traveler fit is ${Math.round(components.group_min_fit * 100)}%.`);
    }
  }

  const friendHistoryFit = components.friend_history_fit || 0;
  const friendLikedBy = recommendation?.history?.friend_liked_by || [];
  const friendRejectedBy = recommendation?.history?.friend_rejected_by || [];
  if (friendHistoryFit >= 0.25 && friendLikedBy.length) {
    reasons.push(`${friendLikedBy.slice(0, 2).join(', ')} already liked this place, so it has group social proof.`);
  } else if (friendHistoryFit <= -0.15 && friendRejectedBy.length) {
    cautions.push(`${friendRejectedBy.slice(0, 2).join(', ')} passed on this before; keep it swappable.`);
  }

  if (recommendation?.swap_impact?.travel_distance_meters !== undefined && recommendation.swap_impact.travel_distance_meters !== null) {
    if (recommendation.swap_impact.travel_distance_meters <= 1200) {
      reasons.push('Keeps the route tight from the previous stop.');
    } else if (recommendation.swap_impact.travel_distance_meters >= 8000) {
      cautions.push('This creates a larger travel jump than ideal for the route.');
    }
  }

  if ((components.chain_penalty || 0) > 0) {
    cautions.push('Chain-like signal is present, so Adventour down-ranked it.');
  }
  if ((components.price_penalty || 0) > 0) {
    cautions.push('May be above the selected or learned price comfort zone.');
  }

  return {
    headline: `Picked for ${stop.label.toLowerCase()} because it fits the route and taste signals.`,
    reasons: reasons.slice(0, 4),
    cautions: cautions.slice(0, 3),
    stats: {
      authenticity: components.authenticity ?? evidence.score,
      hidden_gem_score: evidence.hidden_gem_score,
      chain_risk: evidence.chain_risk,
      travel_distance_meters: recommendation?.swap_impact?.travel_distance_meters,
      member_fit: components.group_fit,
      rescued_member_fit: coverageRescue?.fit ?? null,
      friend_history_fit: Number(friendHistoryFit.toFixed(3)),
    },
  };
};

const priceEstimateForItineraryPlan = (plan: ItineraryPlan) => {
  if (!plan.price_breakdown) {
    return plan.price_breakdown;
  }

  let placeLow = 0;
  let placeHigh = 0;
  plan.days.forEach((day) => {
    day.stops.forEach((stop) => {
      const priceLevel = stop.recommendation.display?.price_level ?? 2;
      const [low, high] = PRICE_LEVEL_ESTIMATES[priceLevel] || PRICE_LEVEL_ESTIMATES[2];
      placeLow += low;
      placeHigh += high;
    });
  });

  const localTransportEstimate = plan.booking_plan?.components
    ?.find((component) => component.type === 'local_transport')
    ?.estimate;
  const localTransitLow = localTransportEstimate?.per_person_low ?? 8 * Math.max(1, plan.days.length);
  const localTransitHigh = localTransportEstimate?.per_person_high ?? 35 * Math.max(1, plan.days.length);
  const perPerson = {
    ...plan.price_breakdown.per_person,
    places_low: placeLow,
    places_high: placeHigh,
    local_transit_low: localTransitLow,
    local_transit_high: localTransitHigh,
    total_known_low: placeLow + localTransitLow,
    total_known_high: placeHigh + localTransitHigh,
  };
  const quotePlan = quotePlanForItineraryPlan(plan, perPerson);
  const travelers = plan.price_breakdown.travelers?.length
    ? plan.price_breakdown.travelers.map((traveler) => ({
      ...traveler,
      known_low: perPerson.total_known_low,
      known_high: perPerson.total_known_high,
      components: traveler.components?.map((component) => {
        if (component.type === 'places') {
          return { ...component, low: placeLow, high: placeHigh };
        }
        if (component.type === 'local_transport') {
          return { ...component, low: localTransitLow, high: localTransitHigh };
        }
        return component;
      }),
    }))
    : plan.price_breakdown.travelers;

  return {
    ...plan.price_breakdown,
    days: plan.days.length,
    nights: Math.max(0, plan.days.length - 1),
    per_person: perPerson,
    travelers,
    quote_plan: quotePlan,
    unknown_cost_components: (quotePlan.items || [])
      .filter((item) => item.quote_required)
      .map((item) => item.type || item.label || 'travel'),
  };
};

const routeAuthenticityForItineraryPlan = (plan: ItineraryPlan): RouteAuthenticityPacket => {
  const stops = plan.days.flatMap((day) => day.stops);
  const stopCount = stops.length;
  if (!stopCount) {
    return {
      status: 'needs_attention',
      headline: 'No stops are ready to prove local authenticity yet.',
      score: 0,
      stop_count: 0,
      average_authenticity: 0,
      local_feeling_count: 0,
      hidden_gem_count: 0,
      generic_risk_count: 0,
      chain_risk_count: 0,
      tourist_trap_risk_count: 0,
      thin_local_evidence_count: 0,
      thin_local_evidence_share: 0,
      average_authenticity_confidence: 0,
      local_feeling_share: 0,
      hidden_gem_share: 0,
      generic_risk_share: 0,
      strongest_local_stops: [],
      risk_stops: [],
      highlights: [],
      warnings: ['Build a route before judging authenticity.'],
      next_actions: ['Seed more local places or widen the route search.'],
    };
  }

  let totalAuthenticity = 0;
  const localFeelingStops: NonNullable<RouteAuthenticityPacket['strongest_local_stops']> = [];
  const hiddenGemStops: NonNullable<RouteAuthenticityPacket['strongest_local_stops']> = [];
  const genericRiskStops: NonNullable<RouteAuthenticityPacket['risk_stops']> = [];
  const chainRiskStops: NonNullable<RouteAuthenticityPacket['risk_stops']> = [];
  const touristRiskStops: NonNullable<RouteAuthenticityPacket['risk_stops']> = [];
  const thinLocalEvidenceStops: NonNullable<RouteAuthenticityPacket['strongest_local_stops']> = [];
  const confidenceValues: number[] = [];

  stops.forEach((stop) => {
    const recommendation = stop.recommendation;
    const evidence = recommendation.authenticity_evidence || {};
    const components = recommendation.components || {};
    const authenticity = components.authenticity ?? evidence.score ?? 0;
    const hiddenGemScore = evidence.hidden_gem_score || 0;
    const chainRisk = evidence.chain_risk || components.chain_penalty || 0;
    const touristTrapScore = evidence.tourist_trap_score || 0;
    const confidence = typeof evidence.confidence === 'number'
      ? evidence.confidence
      : typeof components.authenticity_confidence === 'number'
        ? components.authenticity_confidence
        : null;
    const confidenceStatus = evidence.confidence_status || components.authenticity_confidence_status;
    if (confidence !== null) {
      confidenceValues.push(confidence);
    }
    const stopPayload = {
      slot_id: stop.slot_id,
      label: stop.label,
      name: recommendation.name || recommendation.display?.name || 'Adventour stop',
      authenticity: Number(authenticity.toFixed(3)),
      authenticity_label: evidence.label,
      hidden_gem_score: Number(hiddenGemScore.toFixed(3)),
      chain_risk: Number(chainRisk.toFixed(3)),
      tourist_trap_score: Number(touristTrapScore.toFixed(3)),
      authenticity_confidence: confidence !== null ? Number(confidence.toFixed(3)) : null,
      authenticity_confidence_status: confidenceStatus,
    };

    totalAuthenticity += authenticity;
    if (evidence.label === 'Hidden gem' || evidence.label === 'Local-feeling' || authenticity >= 0.64) {
      localFeelingStops.push(stopPayload);
    }
    if (evidence.label === 'Hidden gem' || hiddenGemScore >= 0.58) {
      hiddenGemStops.push(stopPayload);
    }
    if (confidenceStatus === 'thin' && (evidence.label === 'Hidden gem' || evidence.label === 'Local-feeling' || evidence.label === 'Popular local' || authenticity >= 0.64)) {
      thinLocalEvidenceStops.push(stopPayload);
    }
    if (evidence.label === 'Generic risk' || chainRisk >= 0.3 || touristTrapScore >= 0.35) {
      genericRiskStops.push(stopPayload);
    }
    if (chainRisk >= 0.3) {
      chainRiskStops.push(stopPayload);
    }
    if (touristTrapScore >= 0.35) {
      touristRiskStops.push(stopPayload);
    }
  });

  const averageAuthenticity = totalAuthenticity / stopCount;
  const localShare = localFeelingStops.length / stopCount;
  const hiddenShare = hiddenGemStops.length / stopCount;
  const genericShare = genericRiskStops.length / stopCount;
  const thinShare = thinLocalEvidenceStops.length / stopCount;
  const averageConfidence = confidenceValues.length
    ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
    : 0;
  const score = Math.max(0, Math.min(1, (
    averageAuthenticity * 0.42
    + localShare * 0.30
    + hiddenShare * 0.18
    - genericShare * 0.24
    - thinShare * 0.12
  )));

  const status = genericShare >= 0.45 || score < 0.42
    ? 'needs_attention'
    : thinLocalEvidenceStops.length || localShare < 0.45 || score < 0.62
      ? 'watch'
      : 'ready';
  const headline = status === 'needs_attention'
    ? 'Route may feel too generic for Adventour.'
    : status === 'watch' && thinLocalEvidenceStops.length
      ? 'Route has local texture, but some proof is thin.'
      : status === 'watch'
      ? 'Route has some local texture, but needs stronger hidden-gem coverage.'
      : 'Route has a local-first backbone.';

  const highlights: string[] = [];
  const warnings: string[] = [];
  const nextActions: string[] = [];
  if (localFeelingStops.length) {
    highlights.push(`${localFeelingStops.length} local-feeling stop${localFeelingStops.length === 1 ? '' : 's'} anchor the route.`);
  }
  if (hiddenGemStops.length) {
    highlights.push(`${hiddenGemStops.length} hidden-gem style pick${hiddenGemStops.length === 1 ? '' : 's'} keep it from feeling generic.`);
  }
  if (genericRiskStops.length) {
    warnings.push(`${genericRiskStops.length} stop${genericRiskStops.length === 1 ? '' : 's'} carry generic, chain, or tourist-trap risk.`);
    nextActions.push('Swap the riskiest stop for a local-feeling alternative before sharing this route.');
  }
  if (thinLocalEvidenceStops.length) {
    warnings.push(`${thinLocalEvidenceStops.length} local-feeling stop${thinLocalEvidenceStops.length === 1 ? '' : 's'} need more proof before Adventour should fully trust the route.`);
    nextActions.push('Swipe, rate, or swap thin-proof local stops before sharing this route.');
  }
  if (localShare < 0.45) {
    warnings.push('Less than half the route has strong local/authenticity signal.');
    nextActions.push('Try Hidden gems scout style or widen the range for more local texture.');
  }
  if (!hiddenGemStops.length) {
    warnings.push('No hidden-gem style stop made the route yet.');
    nextActions.push('Use the swap suggestions to add at least one underexposed local stop.');
  }

  return {
    status,
    headline,
    score: Number(score.toFixed(3)),
    stop_count: stopCount,
    average_authenticity: Number(averageAuthenticity.toFixed(3)),
    local_feeling_count: localFeelingStops.length,
    hidden_gem_count: hiddenGemStops.length,
    generic_risk_count: genericRiskStops.length,
    chain_risk_count: chainRiskStops.length,
    tourist_trap_risk_count: touristRiskStops.length,
    thin_local_evidence_count: thinLocalEvidenceStops.length,
    thin_local_evidence_share: Number(thinShare.toFixed(3)),
    average_authenticity_confidence: Number(averageConfidence.toFixed(3)),
    local_feeling_share: Number(localShare.toFixed(3)),
    hidden_gem_share: Number(hiddenShare.toFixed(3)),
    generic_risk_share: Number(genericShare.toFixed(3)),
    strongest_local_stops: [...localFeelingStops]
      .sort((left, right) => ((right.authenticity || 0) - (left.authenticity || 0)) || ((right.hidden_gem_score || 0) - (left.hidden_gem_score || 0)))
      .slice(0, 3),
    risk_stops: [...genericRiskStops]
      .sort((left, right) => ((right.chain_risk || 0) - (left.chain_risk || 0)) || ((right.tourist_trap_score || 0) - (left.tourist_trap_score || 0)))
      .slice(0, 3),
    highlights: highlights.slice(0, 3),
    warnings: warnings.slice(0, 3),
    next_actions: [...new Set(nextActions)].slice(0, 3),
  };
};

const routeReadinessForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['route_readiness'] => {
  const current = plan.route_readiness;
  if (!current) {
    return current;
  }

  const stops = plan.days.flatMap((day) => day.stops);
  const plannedStopCountValue = stops.length;
  const expectedStopCount = current.expected_stop_count || plannedStopCountValue || 1;
  const stopCoverage = Math.min(1, plannedStopCountValue / Math.max(1, expectedStopCount));
  const uniqueGroups = new Set<string>();
  stops.forEach((stop) => {
    diversityGroupsForItineraryRecommendation(stop.recommendation).forEach((group) => uniqueGroups.add(group));
  });
  const varietyScore = Number((uniqueGroups.size / Math.max(1, plannedStopCountValue)).toFixed(3));
  const partyScores = plan.days
    .map((day) => day.party_fit?.fairness_score)
    .filter((score): score is number => typeof score === 'number');
  const partyFairnessScore = partyScores.length
    ? Number((partyScores.reduce((total, score) => total + score, 0) / partyScores.length).toFixed(3))
    : current.party_fairness_score ?? current.party_score;
  const partyCoverageScores = plan.days
    .map((day) => day.party_fit?.coverage_share)
    .filter((score): score is number => typeof score === 'number');
  const partyCoverageScore = partyCoverageScores.length
    ? Number((partyCoverageScores.reduce((total, score) => total + score, 0) / partyCoverageScores.length).toFixed(3))
    : (partyScores.length ? partyFairnessScore : current.party_coverage_score ?? 1);
  const partyScore = Number(clampScore(
    (partyFairnessScore * 0.52) + (partyCoverageScore * 0.48),
  ).toFixed(3));
  const bookingScore = current.booking_score || current.booking_summary?.readiness_score || 0;
  const eventScore = plan.local_events?.summary?.readiness_score ?? current.event_score ?? 0;
  const eventSocialScore = routeEventSocialScoreForSummary(plan.local_events?.summary, plan.local_events?.events?.length);
  const authenticitySummary = plan.route_authenticity || current.authenticity_summary || routeAuthenticityForItineraryPlan(plan);
  const authenticityScore = authenticitySummary.score || 0;
  const score = Number((
    stopCoverage * 0.30
    + varietyScore * 0.17
    + partyScore * 0.17
    + authenticityScore * 0.16
    + bookingScore * 0.12
    + eventScore * 0.08
  ).toFixed(3));
  const label = score >= 0.82
    ? 'Adjusted and ready'
    : score >= 0.62
      ? 'Adjusted route'
      : 'Adjusted with gaps';
  const warnings = new Set(current.warnings || []);
  const strengths = new Set(current.strengths || []);

  if (plannedStopCountValue < expectedStopCount) {
    warnings.add('Route is missing several planned stops.');
  } else {
    warnings.delete('Route is missing several planned stops.');
    strengths.add('All planned stops are filled.');
  }

  if (varietyScore < 0.45 && plannedStopCountValue > 1) {
    warnings.add('Route variety is narrow after swaps.');
  } else if (varietyScore >= 0.6) {
    warnings.delete('Route variety is narrow after swaps.');
    strengths.add('Swaps keep the route varied.');
  }

  if (partyCoverageScore < 1 && (plan.member_count || 1) > 1) {
    warnings.add('At least one traveler lacks a strong route stop.');
  } else if ((plan.member_count || 1) > 1) {
    warnings.delete('At least one traveler lacks a strong route stop.');
  }

  if (partyScore < 0.7 && (plan.member_count || 1) > 1) {
    warnings.add('Friend fit is uneven after swaps.');
  } else if ((plan.member_count || 1) > 1) {
    warnings.delete('Friend fit is uneven after swaps.');
    strengths.add('Swaps keep the party balanced.');
  }

  if (authenticitySummary.status === 'needs_attention') {
    warnings.add(authenticitySummary.headline || 'Route needs stronger local-authentic picks.');
  } else if (authenticitySummary.status === 'watch') {
    warnings.add(authenticitySummary.headline || 'Route authenticity is usable but could improve.');
  } else if (authenticitySummary.status === 'ready') {
    strengths.add(authenticitySummary.headline || 'Route has strong local-authentic texture.');
  }

  if ((plan.local_events?.summary?.route_friend_signal_count || 0) > 0) {
    strengths.add('Friend-backed local events are paired with this route.');
  } else if ((plan.local_events?.summary?.route_social_anchor_count || 0) > 0) {
    strengths.add('Social local events can anchor this Adventour.');
  } else if ((plan.local_events?.summary?.route_match_count || 0) > 0 && plan.local_events?.status === 'ready') {
    warnings.add('Local events are paired, but they need social signal before meetup testing.');
  }

  strengths.add('Updated after your swap.');

  return {
    ...current,
    score,
    label,
    planned_stop_count: plannedStopCountValue,
    expected_stop_count: expectedStopCount,
    stop_coverage: Number(stopCoverage.toFixed(3)),
    variety_score: varietyScore,
    party_score: partyScore,
    party_fairness_score: partyFairnessScore,
    party_coverage_score: partyCoverageScore,
    authenticity_score: authenticityScore,
    authenticity_summary: authenticitySummary,
    booking_score: bookingScore,
    event_score: eventScore,
    event_social_score: eventSocialScore,
    event_social_summary: plan.local_events?.summary?.social_readiness || current.event_social_summary,
    event_summary: plan.local_events?.summary || current.event_summary,
    warnings: Array.from(warnings),
    strengths: Array.from(strengths),
  };
};

const routeEventSocialScoreForSummary = (
  summary?: NonNullable<ItineraryPlan['local_events']>['summary'],
  fallbackEventCount?: number,
) => {
  const socialScore = Math.min(1, Math.max(0, summary?.social_readiness?.score || 0));
  const eventCount = summary?.event_count || fallbackEventCount || 0;
  if (!eventCount) {
    return Number(socialScore.toFixed(3));
  }

  const anchorShare = (summary?.route_social_anchor_count || 0) / Math.max(1, eventCount);
  const friendShare = Math.min(1, (summary?.route_friend_signal_count || 0) / Math.max(1, eventCount));
  const communityShare = Math.min(1, (summary?.route_community_signal_count || 0) / Math.max(1, eventCount));
  const routeSocialSignal = Math.min(1, Math.max(0, anchorShare * 0.5 + friendShare * 0.35 + communityShare * 0.15));
  return Number((socialScore * 0.55 + routeSocialSignal * 0.45).toFixed(3));
};

const prioritizedTestVerdictDimensions = (
  dimensions?: NonNullable<ScenarioReadinessSummary['test_verdict']>['dimensions'],
  limit = 5,
) => {
  const priority: Record<string, number> = {
    model_signal: 0,
    trip_logistics: 1,
    first_swipes: 2,
    social_events: 3,
    friends: 4,
    local: 5,
    route: 6,
    booking: 7,
    depth: 8,
    explanations: 9,
    events: 10,
    swaps: 11,
    cost: 12,
  };

  return [...(dimensions || [])]
    .sort((left, right) => {
      const leftPriority = priority[left.name || ''] ?? 20;
      const rightPriority = priority[right.name || ''] ?? 20;
      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }
      if (left.status === 'fail' && right.status !== 'fail') {
        return -1;
      }
      if (right.status === 'fail' && left.status !== 'fail') {
        return 1;
      }
      return 0;
    })
    .slice(0, limit);
};

const localEventsForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['local_events'] => {
  const localEvents = plan.local_events;
  if (!localEvents?.events?.length) {
    return localEvents;
  }

  let routeMatchCount = 0;
  let routeSocialAnchorCount = 0;
  let routeFriendSignalCount = 0;
  let routeCommunitySignalCount = 0;
  let topRouteEventTitle: string | null = null;
  let topRouteSocialEventTitle: string | null = null;
  const events = localEvents.events.map((event) => {
    const previousRouteReasons = event.route_context?.reasons || [];
    const baseExplanation = (event.explanation || []).filter((reason) => !previousRouteReasons.includes(reason));
    const routeContext = eventRouteContextForPlan(event, plan);

    if (!routeContext) {
      return {
        ...event,
        route_context: undefined,
        explanation: baseExplanation.slice(0, 5),
      };
    }

    routeMatchCount += 1;
    if (!topRouteEventTitle) {
      topRouteEventTitle = event.title;
    }
    const friendSignal = (event.social?.friend_going_count || 0) + (event.social?.friend_interested_count || 0);
    const communitySignal = (event.social?.going_count || 0) + (event.social?.interested_count || 0);
    routeFriendSignalCount += friendSignal;
    routeCommunitySignalCount += communitySignal;
    if (friendSignal || communitySignal || event.event_story?.social_ready) {
      routeSocialAnchorCount += 1;
      if (!topRouteSocialEventTitle) {
        topRouteSocialEventTitle = event.title;
      }
    }

    return {
      ...event,
      route_context: routeContext,
      explanation: [
        ...baseExplanation,
        ...(routeContext.reasons || []).filter((reason) => !baseExplanation.includes(reason)),
      ].slice(0, 5),
    };
  });

  const routeContextMessage = routeMatchCount
    ? 'Local events are paired with nearby route stops.'
    : 'Events are nearby, but Adventour could not pair them to a route stop yet.';

  return {
    ...localEvents,
    events,
    summary: {
      ...localEvents.summary,
      route_match_count: routeMatchCount,
      route_social_anchor_count: routeSocialAnchorCount,
      route_friend_signal_count: routeFriendSignalCount,
      route_community_signal_count: routeCommunitySignalCount,
      top_route_event_title: topRouteEventTitle,
      top_route_social_event_title: topRouteSocialEventTitle,
      route_context_message: routeContextMessage,
      source_summary: localEvents.summary?.source_summary
        ? {
          ...localEvents.summary.source_summary,
          route_match_count: routeMatchCount,
          top_route_event_title: topRouteEventTitle,
          route_context_message: routeContextMessage,
        }
        : localEvents.summary?.source_summary,
    },
  };
};

const routeExplanationForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['route_explanation'] => {
  const stops = plan.days.flatMap((day) => day.stops);
  const uniqueGroups = new Set<string>();
  stops.forEach((stop) => {
    diversityGroupsForItineraryRecommendation(stop.recommendation).forEach((group) => uniqueGroups.add(group));
  });
  const partyScores = plan.days
    .map((day) => day.party_fit?.fairness_score)
    .filter((score): score is number => typeof score === 'number');
  const partyScore = partyScores.length
    ? Number((partyScores.reduce((total, score) => total + score, 0) / partyScores.length).toFixed(3))
    : plan.route_readiness?.party_score;
  const partyCoverageScores = plan.days
    .map((day) => day.party_fit?.coverage_share)
    .filter((score): score is number => typeof score === 'number');
  const partyCoverageScore = partyCoverageScores.length
    ? Number((partyCoverageScores.reduce((total, score) => total + score, 0) / partyCoverageScores.length).toFixed(3))
    : plan.route_readiness?.party_coverage_score;
  const perPerson = plan.price_breakdown?.per_person;
  const routeEventCount = plan.local_events?.summary?.route_match_count || 0;
  const eventTitle = plan.local_events?.summary?.top_route_event_title || plan.local_events?.summary?.top_event_title;
  const reasons: string[] = [];

  if (stops.length) {
    reasons.push(`Updated after your swap with ${stops.length} planned stop${stops.length === 1 ? '' : 's'}.`);
  }
  if (uniqueGroups.size) {
    const groups = Array.from(uniqueGroups)
      .slice(0, 3)
      .map((group) => group.replace(/_/g, ' '))
      .join(', ');
    reasons.push(`Keeps ${groups}${uniqueGroups.size > 3 ? ' and more' : ''} in the route mix.`);
  }
  if ((plan.member_count || 1) > 1 && typeof partyScore === 'number') {
    reasons.push(`Keeps the travel party at ${Math.round(partyScore * 100)}% route fairness.`);
  }
  if ((plan.member_count || 1) > 1 && typeof partyCoverageScore === 'number') {
    reasons.push(`${Math.round(partyCoverageScore * 100)}% of travelers have a strong-fit route stop.`);
  }
  if (routeEventCount) {
    reasons.push(`Still pairs ${routeEventCount} local event${routeEventCount === 1 ? '' : 's'}${eventTitle ? ` including ${eventTitle}` : ''} with route stops.`);
  } else if (plan.local_events?.status === 'ready') {
    reasons.push('Still includes local events near the launch point.');
  }
  if (perPerson) {
    reasons.push(`Known local estimate is $${perPerson.total_known_low}-${perPerson.total_known_high} per person before live flight or stay pricing.`);
  }

  const score = plan.route_readiness?.score || 0;
  const headline = score >= 0.82
    ? 'Your swapped route is still ready to test.'
    : score >= 0.62
      ? 'Your swapped route still works, with a few tradeoffs.'
      : 'Your swapped route needs another look.';

  return {
    ...(plan.route_explanation || {}),
    headline,
    reasons: reasons.length ? reasons.slice(0, 5) : plan.route_explanation?.reasons,
    cautions: plan.route_readiness?.warnings?.slice(0, 3) || plan.route_explanation?.cautions,
    stats: {
      ...(plan.route_explanation?.stats || {}),
      stop_count: stops.length,
      day_count: plan.days.length,
      unique_group_count: uniqueGroups.size,
      variety_score: plan.route_readiness?.variety_score,
      party_score: partyScore,
      authenticity_score: plan.route_readiness?.authenticity_score || plan.route_authenticity?.score,
      booking_score: plan.route_readiness?.booking_score,
      event_score: plan.route_readiness?.event_score,
      route_event_count: routeEventCount,
      known_per_person_low: perPerson?.total_known_low,
      known_per_person_high: perPerson?.total_known_high,
    },
  };
};

const itineraryStoryForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['itinerary_story'] => {
  const stops = plan.days.flatMap((day) => day.stops);
  const uniqueGroups = new Set<string>();
  let localFirstStopCount = 0;
  let hiddenGemStopCount = 0;

  stops.forEach((stop) => {
    diversityGroupsForItineraryRecommendation(stop.recommendation).forEach((group) => uniqueGroups.add(group));
    const evidence = stop.recommendation.authenticity_evidence;
    if ((evidence?.score || 0) >= 0.62) {
      localFirstStopCount += 1;
    }
    if ((evidence?.hidden_gem_score || 0) >= 0.58) {
      hiddenGemStopCount += 1;
    }
  });

  const readinessScore = plan.route_readiness?.score || 0;
  const displayGroups = Array.from(uniqueGroups).slice(0, 3).map((group) => group.replace(/_/g, ' '));
  const groupPhrase = displayGroups.length ? displayGroups.join(', ') : 'local texture';
  const routeStyle = plan.trip_style === 'vacation' ? 'vacation' : 'route';
  const partyScore = plan.route_readiness?.party_score;
  const routeEventCount = plan.local_events?.summary?.route_match_count || 0;
  const perPerson = plan.price_breakdown?.per_person;
  const bookingTimeline = plan.booking_plan?.booking_timeline;
  const bookingSummary = plan.booking_plan?.summary;

  const highlights: string[] = [];
  if (stops.length) {
    highlights.push(`${stops.length} stop${stops.length === 1 ? '' : 's'} across ${plan.days.length} day${plan.days.length === 1 ? '' : 's'}.`);
  }
  if (displayGroups.length) {
    highlights.push(`Route mix covers ${groupPhrase}${uniqueGroups.size > 3 ? ' and more' : ''}.`);
  }
  if (localFirstStopCount) {
    highlights.push(`${localFirstStopCount} stop${localFirstStopCount === 1 ? '' : 's'} carry strong local/authenticity signals.`);
  }
  if (hiddenGemStopCount) {
    highlights.push(`${hiddenGemStopCount} hidden-gem style pick${hiddenGemStopCount === 1 ? '' : 's'} help it avoid a generic checklist.`);
  }
  if ((plan.member_count || 1) > 1 && typeof partyScore === 'number') {
    highlights.push(`Group blend is at ${Math.round(partyScore * 100)}% fairness for ${plan.member_count} travelers.`);
  }
  if (routeEventCount) {
    highlights.push(`${routeEventCount} local event${routeEventCount === 1 ? '' : 's'} line up with the route.`);
  }
  if (perPerson) {
    highlights.push(`Known local spend is estimated at $${perPerson.total_known_low}-${perPerson.total_known_high} per person before live flight or stay pricing.`);
  }

  const planningSteps = [
    bookingTimeline?.headline || bookingSummary?.message,
    ...(plan.route_readiness?.warnings || []).slice(0, 2),
    ...(plan.booking_plan?.next_best_actions || []).slice(0, 2).map((action) => action.label),
  ].filter((item): item is string => Boolean(item));

  return {
    ...(plan.itinerary_story || {}),
    headline: readinessScore >= 0.85
      ? 'A ready-to-launch Adventour with a local-first backbone.'
      : readinessScore >= 0.7
        ? (localFirstStopCount
          ? 'A beta-ready local-first Adventour with clear next steps.'
          : 'A beta-ready Adventour with clear next steps.')
        : stops.length
          ? 'A promising Adventour shell that needs one more pass.'
          : 'Adventour needs more local candidates before this becomes a trip.',
    narrative: `This ${(plan.pace || 'balanced').replace(/_/g, ' ')} ${routeStyle} in ${plan.destination || 'this launch point'} is shaped around ${groupPhrase}, then checked for friend fit, booking readiness, and local-event energy.`,
    highlights: highlights.slice(0, 5),
    planning_steps: planningSteps.slice(0, 4),
    badges: [
      {
        label: plan.route_readiness?.label || 'Route',
        detail: `${Math.round(readinessScore * 100)}% ready`,
        tone: readinessScore >= 0.7 ? 'ready' : 'watch',
      },
      {
        label: 'Local-first',
        detail: stops.length ? `${localFirstStopCount}/${stops.length} stops` : 'Needs candidates',
        tone: localFirstStopCount ? 'ready' : 'watch',
      },
      {
        label: 'Planning',
        detail: (bookingTimeline?.status || plan.booking_plan?.status || 'draft').replace(/_/g, ' '),
        tone: (plan.route_readiness?.booking_score || 0) >= 0.75 ? 'ready' : 'watch',
      },
      ...(routeEventCount || plan.local_events?.summary?.event_count !== undefined ? [{
        label: 'Events',
        detail: `${routeEventCount} paired`,
        tone: routeEventCount ? 'ready' : 'watch',
      }] : []),
    ],
    stats: {
      ...(plan.itinerary_story?.stats || {}),
      local_first_stop_count: localFirstStopCount,
      hidden_gem_stop_count: hiddenGemStopCount,
      stop_count: stops.length,
      day_count: plan.days.length,
      unique_group_count: uniqueGroups.size,
      readiness_score: Number(readinessScore.toFixed(3)),
      booking_timeline_status: bookingTimeline?.status,
      budget_profile: plan.budget_profile,
    },
  };
};

const launchChecklistForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['launch_checklist'] => {
  const stops = plan.days.flatMap((day) => day.stops);
  const plannedStopCount = stops.length;
  const expectedStopCount = plan.route_readiness?.expected_stop_count || plannedStopCount;
  const items: NonNullable<ItineraryPlan['launch_checklist']>['items'] = [];

  if (plannedStopCount > 0) {
    const fullEnough = plannedStopCount >= expectedStopCount;
    items.push({
      id: 'route_stops',
      label: 'Route stops',
      status: fullEnough ? 'ready' : 'warning',
      detail: `${plannedStopCount}/${expectedStopCount} planned stops are filled.`,
      action: fullEnough ? 'Start with the first stop when ready.' : 'Widen the range or try another scout style if you want fuller coverage.',
      blocking: false,
    });
  } else {
    items.push({
      id: 'route_stops',
      label: 'Route stops',
      status: 'action_needed',
      detail: 'No route stops are ready yet.',
      action: 'Rebuild with a broader range, fewer skip filters, or another scout style.',
      blocking: true,
    });
  }

  if (typeof plan.route_readiness?.variety_score === 'number') {
    const varietyReady = plan.route_readiness.variety_score >= 0.45 || plannedStopCount <= 1;
    items.push({
      id: 'route_variety',
      label: 'Route variety',
      status: varietyReady ? 'ready' : 'warning',
      detail: `Route variety is ${Math.round(plan.route_readiness.variety_score * 100)}%.`,
      action: varietyReady ? 'Good mix for a beta route.' : 'Swap a repeated category or compare scout styles.',
      blocking: false,
    });
  }

  if (typeof plan.route_readiness?.party_score === 'number') {
    const partyReady = plan.route_readiness.party_score >= 0.7;
    items.push({
      id: 'party_fit',
      label: 'Party fit',
      status: partyReady ? 'ready' : 'warning',
      detail: `Travel-party fairness is ${Math.round(plan.route_readiness.party_score * 100)}%.`,
      action: partyReady ? 'Balanced enough to test with this group.' : 'Use group-friendly scout style or swap a stop.',
      blocking: false,
    });
  }

  const missingInputs = plan.booking_plan?.missing_inputs || [];
  const bookingSummary = plan.booking_plan?.summary || plan.route_readiness?.booking_summary;
  if (missingInputs.length) {
    items.push({
      id: 'booking_details',
      label: 'Booking details',
      status: 'action_needed',
      detail: `Missing ${missingInputs.join(', ').replace(/_/g, ' ')}.`,
      action: 'Add origin and trip dates before relying on flight or stay steps.',
      blocking: false,
    });
  } else if (bookingSummary) {
    const bookingReady = (bookingSummary.readiness_score || 0) >= 0.75;
    items.push({
      id: 'booking_details',
      label: 'Booking details',
      status: bookingReady ? 'ready' : 'warning',
      detail: bookingSummary.message || 'Booking details can be saved with this route.',
      action: bookingReady ? 'Open provider links and save confirmations as you book.' : 'Review provider steps before starting.',
      blocking: false,
    });
  }

  if (plan.local_events?.status === 'ready') {
    const reservationCount = plan.local_events.summary?.reservation_ready_count || 0;
    items.push({
      id: 'local_events',
      label: 'Local events',
      status: reservationCount ? 'ready' : 'warning',
      detail: `${plan.local_events.summary?.event_count || 0} nearby event picks found.`,
      action: reservationCount ? 'Open event or reservation links before starting.' : 'Review source links for event details.',
      blocking: false,
    });
  } else {
    items.push({
      id: 'local_events',
      label: 'Local events',
      status: 'optional',
      detail: 'No matched local events yet.',
      action: 'Use source searches or add an event manually if this trip needs a social anchor.',
      blocking: false,
    });
  }

  const blocking_count = items.filter((item) => item.blocking).length;
  const action_count = items.filter((item) => item.status === 'action_needed').length;
  const warning_count = items.filter((item) => item.status === 'warning').length;
  const can_start = plannedStopCount > 0 && blocking_count === 0;
  const headline = !can_start
    ? 'Finish the route shell before starting.'
    : action_count || warning_count
      ? 'Startable, with a few things to review.'
      : 'Ready to launch.';

  return {
    can_start,
    headline,
    blocking_count,
    action_count,
    warning_count,
    items,
  };
};

const scenarioReadinessForItineraryPlan = (plan: ItineraryPlan): ScenarioReadinessSummary | undefined => {
  const current = plan.scenario_readiness;
  const route = plan.route_readiness;
  if (!route) {
    return current;
  }

  const launchChecklist = plan.launch_checklist || launchChecklistForItineraryPlan(plan);
  const stops = plan.days.flatMap((day) => day.stops);
  const swapReadyStops = stops.filter((stop) => (stop.alternatives || []).length > 0).length;
  const stopCoverage = route.stop_coverage ?? (stops.length / Math.max(1, route.expected_stop_count || stops.length || 1));
  const swapCoverage = stops.length ? swapReadyStops / stops.length : 0;
  const bookingScore = route.booking_score ?? route.booking_summary?.readiness_score ?? 0;
  const eventScore = route.event_score ?? 0;
  const eventSocialScore = route.event_social_score ?? 0;
  const localScore = route.authenticity_score ?? route.authenticity_summary?.score ?? 0;
  const routeScore = route.score ?? 0;
  const friendReadiness = current?.friend_readiness || null;
  const friendReady = !friendReadiness || friendReadiness.status === 'ready' || (friendReadiness.status === 'watch' && (friendReadiness.coverage_share || 0) >= 0.75);
  const canStart = launchChecklist?.can_start !== false;
  const blockers = [
    ...(!canStart ? [launchChecklist?.headline || 'Route must be launchable before friend testing.'] : []),
    ...(friendReadiness?.status === 'needs_attention' ? [friendReadiness.headline || 'At least one friend needs a stronger match.'] : []),
    ...(bookingScore < 0.45 ? ['Booking details need more setup before this route feels testable.'] : []),
  ].filter(Boolean);
  const warnings = new Set<string>([
    ...(route.warnings || []),
    ...(current?.warnings || []),
  ]);
  const strengths = new Set<string>([
    ...(route.strengths || []),
    ...(current?.strengths || []),
  ]);
  const nextActions = new Set<string>(current?.next_actions || []);

  if (eventSocialScore >= 0.5) {
    strengths.add('Local events have enough social signal to test as meetup anchors.');
    warnings.delete('Local events need more social signal before meetup testing.');
  } else if ((plan.local_events?.summary?.event_count || 0) > 0) {
    warnings.add('Local events need more social signal before meetup testing.');
    nextActions.add('Ask friends to mark Interested/Going on event anchors.');
  }
  if (swapCoverage >= 0.75) {
    strengths.add('Most route stops have swap options.');
  } else if (stops.length) {
    warnings.add('Some route stops have limited swap flexibility.');
    nextActions.add('Compare scout styles or rebuild if you want more swap options.');
  }
  if (bookingScore >= 0.75) {
    strengths.add('Booking and reservation packet is usable.');
  }

  const status: ScenarioReadinessSummary['status'] = blockers.length
    ? 'needs_attention'
    : canStart && routeScore >= 0.72 && bookingScore >= 0.55 && friendReady
      ? 'ready'
      : 'watch';
  const betaTestable = status !== 'needs_attention' && canStart && stopCoverage >= 0.75;
  const friendTestable = status === 'ready';
  const headline = status === 'ready'
    ? 'Ready to send to trusted friends.'
    : status === 'needs_attention'
      ? 'Tune this route before friend testing.'
      : 'Usable for beta testing, but review the watchouts.';

  const dimensions = [
    {
      name: 'route',
      label: 'Route',
      score: Number(routeScore.toFixed(3)),
      status: routeScore >= 0.72 ? 'pass' : routeScore >= 0.55 ? 'warn' : 'fail',
      summary: route.label || 'Route readiness recalculated from the current plan.',
    },
    {
      name: 'booking',
      label: 'Booking',
      score: Number(bookingScore.toFixed(3)),
      status: bookingScore >= 0.72 ? 'pass' : bookingScore >= 0.45 ? 'warn' : 'fail',
      summary: route.booking_summary?.message || 'Booking packet refreshed from the current plan.',
    },
    {
      name: 'events',
      label: 'Local events',
      score: Number(eventScore.toFixed(3)),
      status: eventScore >= 0.72 ? 'pass' : eventScore >= 0.45 ? 'warn' : 'fail',
      summary: route.event_summary?.route_context_message || 'Local-event readiness refreshed from the current plan.',
    },
    {
      name: 'social_events',
      label: 'Social events',
      score: Number(eventSocialScore.toFixed(3)),
      status: eventSocialScore >= 0.5 ? 'pass' : eventSocialScore > 0 ? 'warn' : 'unknown',
      summary: route.event_social_summary?.headline || 'Social event pulse refreshed from current local-event interest.',
    },
    {
      name: 'local',
      label: 'Local texture',
      score: Number(localScore.toFixed(3)),
      status: localScore >= 0.62 ? 'pass' : localScore >= 0.42 ? 'warn' : 'fail',
      summary: route.authenticity_summary?.headline || 'Authenticity checked from current route stops.',
    },
  ];
  const remediationPlan = current?.remediation_plan?.length
    ? current.remediation_plan
    : compactUniqueText([...blockers, ...Array.from(nextActions)])
      .slice(0, 3)
      .map((action, index) => ({
        id: index === 0 && blockers.length ? 'route_blocker' : `route_action_${index + 1}`,
        label: index === 0 && blockers.length ? 'Route blocker' : 'Route repair',
        severity: index === 0 && blockers.length ? 'needs_attention' : 'watch',
        actions: [action],
      }));

  return {
    ...(current || {}),
    mode: 'planned_itinerary',
    status,
    ready_for_friend_testing: friendTestable,
    beta_testable: betaTestable,
    headline,
    metrics: {
      ...(current?.metrics || {}),
      route_score: Number(routeScore.toFixed(3)),
      stop_coverage: Number(stopCoverage.toFixed(3)),
      swap_coverage: Number(swapCoverage.toFixed(3)),
      booking_score: Number(bookingScore.toFixed(3)),
      event_score: Number(eventScore.toFixed(3)),
      event_social_score: Number(eventSocialScore.toFixed(3)),
      authenticity_score: Number(localScore.toFixed(3)),
    },
    checks: dimensions.map((dimension) => ({
      name: dimension.name,
      label: dimension.label,
      status: dimension.status,
      value: dimension.score,
      message: dimension.summary,
    })),
    test_verdict: {
      ...(current?.test_verdict || {}),
      status,
      headline,
      score: Number((
        routeScore * 0.28
        + stopCoverage * 0.18
        + bookingScore * 0.18
        + eventScore * 0.12
        + eventSocialScore * 0.10
        + localScore * 0.14
      ).toFixed(3)),
      friend_testable: friendTestable,
      dimensions,
      blockers,
      next_actions: Array.from(nextActions).slice(0, 4),
    },
    strengths: Array.from(strengths).slice(0, 5),
    warnings: Array.from(warnings).slice(0, 5),
    next_actions: Array.from(nextActions).slice(0, 5),
    remediation_plan: remediationPlan,
    friend_readiness: friendReadiness,
  };
};

const tripPacketEventPromptsForItineraryPlan = (plan: ItineraryPlan): NonNullable<TripPacket['save_prompts']> => {
  const events = plan.local_events?.events || [];
  const routeEvents = events.filter((event) => (
    event.route_context && (event.reservation_url || event.source_url)
  ));
  const fallbackEvents = events.filter((event) => (
    !event.route_context && event.reservation_url
  ));
  const prompts: NonNullable<TripPacket['save_prompts']> = [];
  const seen = new Set<string>();

  [...routeEvents, ...fallbackEvents].forEach((event) => {
    const promptId = `event_${event.id || event.title || event.reservation_url || event.source_url}`;
    if (seen.has(promptId)) {
      return;
    }
    seen.add(promptId);

    const routeContext = event.route_context;
    const label = event.reservation_url
      ? `RSVP: ${event.title || 'Local event'}`
      : `Check event: ${event.title || 'Local event'}`;
    const baseDetail = event.reservation_url
      ? 'Open the event RSVP, then save the confirmation in Adventour.'
      : 'Open the event source and confirm details before relying on it.';
    const detail = routeContext?.fit_label
      ? `${baseDetail} Paired with ${routeContext.fit_label.toLowerCase()}.`
      : baseDetail;

    prompts.push({
      id: promptId,
      label,
      detail,
      reservation_type: 'event',
      provider: event.source_name || event.source?.source_name || event.source?.badge || null,
      source_url: event.source_url || null,
      reservation_url: event.reservation_url || null,
      starts_at: event.starts_at || null,
      route_context: routeContext ? {
        day: routeContext.day,
        slot_id: routeContext.slot_id,
        fit_label: routeContext.fit_label,
        distance_to_stop_meters: routeContext.distance_to_stop_meters,
      } : null,
    });
  });

  return prompts.slice(0, 4);
};

const bookingChecklistForItineraryPlan = (plan: ItineraryPlan): BookingChecklist | undefined => {
  const current = plan.booking_plan?.booking_checklist || plan.trip_packet?.booking_checklist;
  if (current?.items?.length) {
    return current;
  }
  const bookingPlan = plan.booking_plan;
  if (!bookingPlan) {
    return undefined;
  }

  const missingInputs = bookingPlan.missing_inputs || bookingPlan.summary?.missing_inputs || [];
  const actionLinks = bookingPlan.booking_action_links || [];
  const timelineItems = bookingPlan.booking_timeline?.items || [];
  const localTransport = (bookingPlan.components || []).find((component) => component.type === 'local_transport');
  const providerLinkCount = actionLinks.filter((link) => link.url).length;
  const saveReadyCount = Math.max(
    bookingPlan.booking_handoff?.ready_to_save_count || 0,
    timelineItems.filter((item) => item.stores_reservation).length,
  );
  const readableMissing = missingInputs.map((item) => String(item).replace(/_/g, ' ')).join(', ');

  const items: NonNullable<BookingChecklist['items']> = [
    missingInputs.length ? {
      id: 'trip_basics',
      label: 'Trip basics',
      status: 'action_needed',
      detail: `Missing ${readableMissing}.`,
      action: `Add ${readableMissing} before booking this route.`,
      blocking: true,
      missing_inputs: missingInputs,
    } : {
      id: 'trip_basics',
      label: 'Trip basics',
      status: 'ready',
      detail: 'Destination, party size, and route context are ready enough for booking setup.',
      action: 'Review the generated booking links when you are ready to compare options.',
      blocking: false,
      missing_inputs: [],
    },
    {
      id: 'provider_links',
      label: 'Provider links',
      status: providerLinkCount ? 'ready' : 'manual',
      detail: providerLinkCount ? `${providerLinkCount} booking links prepared.` : 'No provider links are ready yet.',
      action: providerLinkCount
        ? 'Open a booking link, compare options, then save the confirmation here.'
        : 'Use manual booking searches until provider links are connected.',
      blocking: Boolean(missingInputs.length),
      link_count: providerLinkCount,
      quote_ready_count: bookingPlan.booking_handoff?.ready_to_quote_count || 0,
    },
    {
      id: 'reservation_wallet',
      label: 'Reservation wallet',
      status: bookingPlan.reservation_storage?.status === 'ready' ? 'ready' : 'manual',
      detail: bookingPlan.reservation_storage?.status === 'ready'
        ? `${saveReadyCount} save-ready slots can store confirmations.`
        : 'Reservation storage is not connected yet.',
      action: 'After booking, save provider, confirmation number, cost, and notes in Adventour.',
      blocking: bookingPlan.reservation_storage?.status !== 'ready',
      save_ready_count: saveReadyCount,
    },
  ];

  if (localTransport) {
    items.push({
      id: 'local_transport',
      label: 'Local travel',
      status: localTransport.status === 'estimated' ? 'ready' : 'manual',
      detail: localTransport.setup || localTransport.action || 'Choose how the group will move between stops.',
      action: localTransport.setup_steps?.[0] || localTransport.action || 'Pick local transport before starting the route.',
      blocking: false,
      provider: localTransport.setup_provider,
      source_url: localTransport.setup_source_url,
    });
  }

  items.push({
    id: 'tickets_and_rsvps',
    label: 'Tickets and RSVPs',
    status: 'manual',
    detail: 'Timed-entry stops and local events can be booked externally and saved here.',
    action: 'Open event or place links, then save reservation notes in Adventour.',
    blocking: false,
  });

  const blockingCount = items.filter((item) => item.blocking).length;
  const readyCount = items.filter((item) => item.status === 'ready').length;
  const actionCount = items.filter((item) => item.status === 'action_needed' || item.status === 'manual').length;
  const nextItem = items.find((item) => item.blocking) || items.find((item) => item.status !== 'ready');

  return {
    status: blockingCount ? 'needs_details' : actionCount ? 'ready_with_manual_steps' : 'ready',
    headline: blockingCount
      ? 'A few trip basics are blocking the booking packet.'
      : actionCount
        ? 'Booking is usable; Adventour marked the manual pieces.'
        : 'Booking, saving, and local setup are ready.',
    readiness_score: bookingPlan.summary?.readiness_score,
    blocking_count: blockingCount,
    ready_count: readyCount,
    action_count: actionCount,
    next_action: nextItem?.action || bookingPlan.booking_handoff?.next_step,
    items,
  };
};

const eventPacketForItineraryPlan = (plan: ItineraryPlan): TripEventPacket | undefined => {
  const current = plan.trip_packet?.event_packet;
  if (current?.status) {
    return current;
  }
  const localEvents = plan.local_events;
  if (!localEvents) {
    return undefined;
  }

  const summary = localEvents.summary || {};
  const socialReadiness = summary.social_readiness || {};
  const sourceSummary = summary.source_summary || {};
  const recommendedSource = sourceSummary.recommended_external_source;
  const routeSocialAnchor = summary.route_social_anchor;
  const eventPlan = localEvents.event_plan;
  const eventCount = summary.event_count ?? localEvents.events?.length ?? 0;
  const routeMatchCount = summary.route_match_count || 0;
  const reservationReadyCount = summary.route_reservation_ready_count || summary.reservation_ready_count || 0;
  const friendSignalCount = summary.route_friend_signal_count || socialReadiness.friend_signal_count || 0;
  const topEventTitle = routeSocialAnchor?.title
    || summary.top_route_event_title
    || summary.top_event_title
    || socialReadiness.top_social_event?.title
    || null;
  const meetupAnchorEvent = localEvents.events?.find(event =>
    (routeSocialAnchor?.id && event.id === routeSocialAnchor.id)
    || (routeSocialAnchor?.title && event.title === routeSocialAnchor.title)
    ||
    (socialReadiness.top_social_event?.id && event.id === socialReadiness.top_social_event.id)
    || (socialReadiness.top_social_event?.title && event.title === socialReadiness.top_social_event.title)
  ) || localEvents.events?.find(event => event.route_context) || localEvents.events?.[0];

  const status: TripEventPacket['status'] = socialReadiness.status === 'ready'
    || (routeMatchCount > 0 && reservationReadyCount > 0)
    ? 'ready'
    : eventCount > 0
      ? 'needs_confirmation'
      : 'needs_scouting';
  const headline = status === 'ready'
    ? friendSignalCount > 0
      ? socialReadiness.headline || 'A local event can anchor this Adventour socially.'
      : `${topEventTitle || 'A local event'} is paired with the route and ready to reserve.`
    : status === 'needs_confirmation'
      ? 'Local event leads found; confirm source, RSVP, or friend interest.'
      : 'No saved local event anchor yet; scout current calendars before relying on this route socially.';

  return {
    status,
    headline,
    score: summary.readiness_score,
    social_status: socialReadiness.status,
    social_score: socialReadiness.score,
    event_plan_status: eventPlan?.status,
    short_label: status === 'ready' && friendSignalCount
      ? 'Social ready'
      : routeMatchCount
        ? `${routeMatchCount} paired`
        : eventCount
          ? `${eventCount} leads`
          : 'Scout',
    event_count: eventCount,
    route_match_count: routeMatchCount,
    reservation_ready_count: reservationReadyCount,
    friend_signal_count: friendSignalCount,
    community_signal_count: socialReadiness.community_signal_count || summary.route_community_signal_count || 0,
    top_event_title: topEventTitle,
    top_event: socialReadiness.top_social_event,
    route_social_anchor: routeSocialAnchor,
    meetup_anchor: meetupAnchorEvent ? {
      id: meetupAnchorEvent.id,
      title: meetupAnchorEvent.title,
      category: meetupAnchorEvent.category,
      starts_at: meetupAnchorEvent.starts_at,
      source_name: meetupAnchorEvent.source_name || meetupAnchorEvent.source?.source_name || meetupAnchorEvent.source?.badge,
      source_badge: meetupAnchorEvent.source?.badge,
      source_url: meetupAnchorEvent.source_url,
      reservation_url: meetupAnchorEvent.reservation_url,
      action_url: meetupAnchorEvent.reservation_url || meetupAnchorEvent.source_url,
      reservation_ready: Boolean(meetupAnchorEvent.reservation_url),
      friend_signal_count: (meetupAnchorEvent.social?.friend_going_count || 0) + (meetupAnchorEvent.social?.friend_interested_count || 0),
      community_signal_count: (meetupAnchorEvent.social?.going_count || 0) + (meetupAnchorEvent.social?.interested_count || 0),
      score: meetupAnchorEvent.score,
      reason: meetupAnchorEvent.route_context?.fit_label
        ? `Best event fit for ${meetupAnchorEvent.route_context.fit_label}.`
        : 'Best local event lead for this Adventour.',
      next_action: meetupAnchorEvent.reservation_url
        ? 'Open the RSVP or ticket page, then save the confirmation in Adventour.'
        : meetupAnchorEvent.source_url
          ? 'Open the event source and confirm details.'
          : socialReadiness.next_action,
      route_context: meetupAnchorEvent.route_context,
    } : null,
    next_action: socialReadiness.next_action
      || eventPlan?.items?.[0]?.action
      || recommendedSource?.reason
      || 'Scout current local calendars or add a local event.',
    meetup_checklist: socialReadiness.meetup_checklist || [],
    blocking_count: socialReadiness.blocking_count || 0,
    recommended_source: recommendedSource,
    event_plan_items: eventPlan?.items?.slice(0, 4) || [],
  };
};

const compactUniqueText = (values: (string | undefined | null)[], limit = 4) => {
  const compacted: string[] = [];
  values.forEach((value) => {
    const text = String(value || '').trim();
    if (text && !compacted.includes(text) && compacted.length < limit) {
      compacted.push(text);
    }
  });
  return compacted;
};

const friendTestPacketForItineraryPlan = (plan: ItineraryPlan): TripFriendTestPacket | undefined => {
  const current = plan.trip_packet?.friend_test_packet;
  if (current?.status) {
    return current;
  }

  const scenario = plan.scenario_readiness || scenarioReadinessForItineraryPlan(plan);
  if (!scenario) {
    return undefined;
  }

  const verdict = scenario.test_verdict || {};
  const friendReadiness = scenario.friend_readiness || undefined;
  const suggestedSwaps = [
    ...(friendReadiness?.suggested_swaps || []),
    ...((friendReadiness?.underserved_members || []).flatMap((member) => member.suggested_swaps || [])),
  ];
  const status = verdict.status || scenario.status || friendReadiness?.status || 'watch';
  const headline = verdict.headline
    || friendReadiness?.headline
    || scenario.headline
    || 'Adventour checked whether this route is ready to test with friends.';

  return {
    status,
    headline,
    score: verdict.score ?? null,
    friend_testable: Boolean(verdict.friend_testable || scenario.ready_for_friend_testing),
    beta_testable: Boolean(scenario.beta_testable),
    member_count: friendReadiness?.member_count || scenario.metrics?.member_count || 0,
    covered_member_count: friendReadiness?.covered_member_count || 0,
    underserved_count: friendReadiness?.underserved_count || 0,
    coverage_share: friendReadiness?.coverage_share ?? scenario.metrics?.member_coverage_share ?? null,
    average_group_fit: friendReadiness?.average_group_fit ?? scenario.metrics?.average_group_fit ?? null,
    friend_readiness_status: friendReadiness?.status,
    friend_readiness_headline: friendReadiness?.headline,
    blockers: compactUniqueText([...(verdict.blockers || []), ...(scenario.warnings || [])], 3),
    next_actions: compactUniqueText([
      ...(verdict.next_actions || []),
      ...(friendReadiness?.next_actions || []),
      ...(scenario.next_actions || []),
    ], 4),
    dimensions: verdict.dimensions?.slice(0, 6) || [],
    suggested_swaps: suggestedSwaps.slice(0, 3),
  };
};

const routeModelConfidenceForItineraryPlan = (plan: ItineraryPlan): ModelConfidenceSummary | undefined => {
  const current = plan.route_model_confidence || plan.trip_packet?.route_model_confidence;
  const base = current || plan.recommendation_quality?.model_confidence;
  const route = plan.route_readiness;
  if (!base && !route) {
    return undefined;
  }

  const asNumber = (value: unknown, fallback = 0) => {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : fallback;
  };
  const stopCoverage = asNumber(route?.stop_coverage, asNumber(base?.stop_coverage));
  const authenticityScore = asNumber(route?.authenticity_score ?? route?.authenticity_summary?.score, asNumber(base?.authenticity_score));
  const partyScore = asNumber(route?.party_score, asNumber(base?.party_score));
  const bookingScore = asNumber(route?.booking_score, asNumber(base?.booking_score));
  const swapCoverage = asNumber(plan.swap_guide?.swap_coverage, asNumber(base?.swap_coverage));
  const modelScore = asNumber(base?.score);
  const learnedGuard = base?.learned_rerank?.guard_status;
  const learnedPenalty = learnedGuard === 'constrained' ? 0.08 : learnedGuard === 'watch' ? 0.04 : 0;
  const score = Math.max(0, Math.min(1, (
    modelScore * 0.34
    + stopCoverage * 0.18
    + authenticityScore * 0.16
    + partyScore * 0.12
    + bookingScore * 0.10
    + swapCoverage * 0.10
    - learnedPenalty
  )));
  const warnings = compactUniqueText([
    ...(base?.warnings || []),
    stopCoverage < 0.8 ? 'The route has fewer filled stops than ideal, so model confidence is capped.' : undefined,
    authenticityScore < 0.65 ? 'Route-level local/authenticity signal is weaker than Adventour prefers.' : undefined,
    swapCoverage < 0.75 ? 'Some stops have limited swap flexibility.' : undefined,
  ], 5);
  const basis = compactUniqueText([
    ...(base?.basis || []),
    stopCoverage >= 0.8 ? 'The planned route kept enough slots filled to trust the itinerary shape.' : undefined,
    authenticityScore >= 0.65 ? 'Local/authenticity guardrails stayed strong after building the route.' : undefined,
    partyScore >= 0.7 && (plan.member_count || 1) > 1 ? 'Friend blending still looks balanced across planned stops.' : undefined,
    swapCoverage >= 0.75 ? 'Most planned stops have swap options, so testers can tune the route.' : undefined,
  ], 6);
  const nextActions = compactUniqueText([
    ...(base?.next_actions || []),
    stopCoverage < 0.8 ? 'Widen the range or compare scout styles to fill the route.' : undefined,
    authenticityScore < 0.65 ? 'Swap in a stronger local-feeling stop before sharing.' : undefined,
  ], 5);
  const status: ModelConfidenceSummary['status'] = score >= 0.72
    ? 'ready'
    : score >= 0.46
      ? 'learning'
      : 'cold_start';

  return {
    ...base,
    status,
    headline: status === 'ready'
      ? 'Route model signal is strong enough to test.'
      : status === 'learning'
        ? 'Route model signal is usable, but keep tuning.'
        : 'Route model signal is early; rely on local guardrails and swaps.',
    score: Number(score.toFixed(3)),
    stop_coverage: Number(stopCoverage.toFixed(3)),
    authenticity_score: Number(authenticityScore.toFixed(3)),
    party_score: Number(partyScore.toFixed(3)),
    booking_score: Number(bookingScore.toFixed(3)),
    swap_coverage: Number(swapCoverage.toFixed(3)),
    basis,
    warnings,
    next_actions: nextActions,
  };
};

const betaReadinessDimension = (
  id: string,
  label: string,
  scoreValue: number | undefined | null,
  weight: number,
  evidence: string,
  action: string,
  passMin = 0.7,
  watchMin = 0.5,
  optional = false,
): NonNullable<NonNullable<TripPacket['beta_readiness']>['dimensions']>[number] => {
  const score = Math.max(0, Math.min(1, Number(scoreValue || 0)));
  const status = score >= passMin ? 'pass' : score >= watchMin ? 'watch' : 'fail';
  return {
    id,
    label,
    score: Number(score.toFixed(3)),
    weight,
    status,
    optional,
    evidence,
    action,
  };
};

const betaReadinessForItineraryPlan = (
  plan: ItineraryPlan,
  packets: {
    current?: TripPacket;
    eventPacket?: TripEventPacket;
    swapGuide?: SwapGuide;
    routeModelConfidence?: ModelConfidenceSummary;
    authenticityPacket?: RouteAuthenticityPacket;
  },
): TripPacket['beta_readiness'] => {
  if (packets.current?.beta_readiness?.status) {
    return packets.current.beta_readiness;
  }

  const memberCount = packets.routeModelConfidence?.member_count || plan.member_count || 1;
  const eventStatus = packets.eventPacket?.status;
  const eventScore = eventStatus === 'ready'
    ? 1
    : eventStatus === 'needs_confirmation'
      ? 0.68
      : eventStatus === 'needs_scouting'
        ? 0.52
        : plan.route_readiness?.event_score || 0.5;
  const dimensions = [
    betaReadinessDimension(
      'route',
      'Route shape',
      plan.route_readiness?.score,
      0.18,
      'Route has enough complete, varied stops to test.',
      'Fill route gaps or compare scout styles.',
      0.7,
      0.55,
    ),
    betaReadinessDimension(
      'model',
      'Model confidence',
      packets.routeModelConfidence?.score,
      0.16,
      'Recommendation model signal is strong enough for a beta run.',
      'Collect more accepts/rejects or use safer local-first guardrails.',
      0.66,
      0.48,
    ),
    betaReadinessDimension(
      'local_promise',
      'Local promise',
      packets.authenticityPacket?.score || plan.route_readiness?.authenticity_score,
      0.17,
      "The route keeps Adventour's local-first promise.",
      'Swap out generic-risk stops for local-feeling alternatives.',
      0.68,
      0.52,
    ),
    betaReadinessDimension(
      'booking',
      'Planning handoff',
      plan.trip_logistics_readiness?.score || plan.route_readiness?.booking_score,
      0.16,
      'Booking links, setup steps, and reservation storage are usable.',
      'Add missing trip details or provider links before sharing.',
      0.72,
      0.55,
    ),
    betaReadinessDimension(
      'friend_fit',
      'Friend fit',
      memberCount > 1 ? plan.route_readiness?.party_score : 1,
      memberCount > 1 ? 0.14 : 0.06,
      'The route is balanced enough for the selected travelers.',
      'Use group-friendly swaps for any underserved friend.',
      0.7,
      0.55,
      memberCount <= 1,
    ),
    betaReadinessDimension(
      'swap_safety',
      'Swap safety',
      packets.swapGuide?.swap_coverage,
      0.1,
      'Most stops have safe alternatives if a tester dislikes one.',
      'Widen range or rebuild to add more alternatives.',
      0.7,
      0.45,
    ),
    betaReadinessDimension(
      'local_events',
      'Local events',
      eventScore,
      0.09,
      'Local event or scouting guidance is ready enough for social testing.',
      'Scout current local calendars or add a meetup anchor.',
      0.7,
      0.48,
    ),
  ];
  const totalWeight = dimensions.reduce((sum, dimension) => sum + (dimension.weight || 0), 0) || 1;
  const score = dimensions.reduce((sum, dimension) => sum + (dimension.score || 0) * (dimension.weight || 0), 0) / totalWeight;
  const blocking = dimensions.filter((dimension) => dimension.status === 'fail' && !dimension.optional);
  const watchouts = dimensions.filter((dimension) => dimension.status === 'watch' && !dimension.optional);
  const weakestDimension = [...dimensions].sort((a, b) => (a.score || 0) - (b.score || 0))[0] || null;
  const ready = score >= 0.74 && blocking.length === 0;
  const status = ready && watchouts.length === 0
    ? 'ready'
    : ready
      ? 'beta_ready_with_notes'
      : score >= 0.58
        ? 'needs_tuning'
        : 'not_ready';

  return {
    status,
    headline: status === 'ready'
      ? 'Ready for close-friend testing.'
      : status === 'beta_ready_with_notes'
        ? 'Ready to test, with a few notes.'
        : status === 'needs_tuning'
          ? 'Promising, but tune before friend testing.'
          : 'Not ready for friend testing yet.',
    score: Number(score.toFixed(3)),
    ready_for_friend_testing: ready,
    member_count: memberCount,
    weakest_dimension: weakestDimension,
    blocking_count: blocking.length,
    watch_count: watchouts.length,
    dimensions,
    strengths: dimensions.filter((dimension) => dimension.status === 'pass').slice(0, 3).map((dimension) => dimension.evidence || '').filter(Boolean),
    required_actions: blocking.slice(0, 3).map((dimension) => dimension.action || '').filter(Boolean),
    watchouts: watchouts.slice(0, 3).map((dimension) => dimension.action || '').filter(Boolean),
    next_action: blocking[0]?.action || watchouts[0]?.action || 'Share this Adventour with a trusted tester or start it yourself.',
  };
};

const tripPacketForItineraryPlan = (plan: ItineraryPlan): TripPacket | undefined => {
  const current = plan.trip_packet;
  const bookingPlan = plan.booking_plan;
  const bookingSummary = bookingPlan?.summary || plan.route_readiness?.booking_summary;
  const bookingChecklist = bookingChecklistForItineraryPlan(plan);
  const authenticityPacket = plan.route_authenticity || plan.route_readiness?.authenticity_summary || current?.authenticity_packet || routeAuthenticityForItineraryPlan(plan);
  const eventPacket = eventPacketForItineraryPlan(plan);
  const friendTestPacket = friendTestPacketForItineraryPlan(plan);
  const swapGuide = swapGuideForItineraryPlan(plan);
  const routeModelConfidence = routeModelConfidenceForItineraryPlan({ ...plan, swap_guide: swapGuide });
  const betaReadiness = betaReadinessForItineraryPlan(plan, {
    current,
    eventPacket,
    swapGuide,
    routeModelConfidence,
    authenticityPacket,
  });
  const launchChecklist = plan.launch_checklist || launchChecklistForItineraryPlan(plan);
  const perPerson = plan.price_breakdown?.per_person;
  const missingInputs = bookingPlan?.missing_inputs || bookingSummary?.missing_inputs || current?.missing_inputs || [];
  const knownLow = perPerson?.total_known_low;
  const knownHigh = perPerson?.total_known_high;
  const quotePlan = plan.price_breakdown?.quote_plan || current?.quote_plan || current?.cost_confidence?.quote_plan || quotePlanForItineraryPlan(plan, perPerson);
  const bookingScore = plan.route_readiness?.booking_score ?? bookingSummary?.readiness_score ?? current?.booking_score ?? 0;
  const canStart = launchChecklist?.can_start !== false;
  const eventReservationCount = (
    plan.local_events?.summary?.route_reservation_ready_count
    || plan.local_events?.summary?.reservation_ready_count
    || 0
  );
  const eventPrompts = tripPacketEventPromptsForItineraryPlan(plan);
  const nonEventSavePrompts = (current?.save_prompts || []).filter((prompt) => prompt.reservation_type !== 'event');
  const savePrompts = [...nonEventSavePrompts, ...eventPrompts].slice(0, 6);
  const nonEventBookingLinks = (current?.booking_links || []).filter((link) => link.reservation_type !== 'event');
  const fallbackBookingLinks = bookingPlan?.booking_action_links?.map((link) => ({
    id: link.id,
    label: link.label,
    provider_label: link.provider_label,
    url: link.url,
    stores_reservation: Boolean(link.stores_reservation),
    reservation_type: link.reservation_type,
  })) || [];
  const baseBookingLinks = nonEventBookingLinks.length ? nonEventBookingLinks : fallbackBookingLinks;
  const eventBookingLinks = eventPrompts
    .filter((prompt) => prompt.reservation_url || prompt.source_url)
    .map((prompt) => ({
      id: prompt.id,
      label: prompt.label,
      provider_label: prompt.provider || undefined,
      url: prompt.reservation_url || prompt.source_url,
      stores_reservation: true,
      reservation_type: 'event',
    }));
  const bookingLinks = [
    ...baseBookingLinks.slice(0, 2),
    ...eventBookingLinks.slice(0, 2),
    ...baseBookingLinks.slice(2),
  ].slice(0, 4);

  const costLabel = typeof knownLow === 'number' && typeof knownHigh === 'number'
    ? `$${knownLow}-${knownHigh} known per person`
    : current?.known_per_person?.label;
  const saveableTimelineCount = bookingPlan?.booking_timeline?.items?.filter((item) => item.stores_reservation).length || 0;
  const status: TripPacket['status'] = missingInputs.length
    ? 'needs_details'
    : bookingScore >= 0.85 && canStart
      ? 'ready'
      : canStart
        ? 'action_needed'
        : 'blocked';
  const headline = status === 'needs_details'
    ? 'Add a few trip details before this Adventour is booking-ready.'
    : status === 'ready'
      ? 'This Adventour has a clear booking packet.'
      : status === 'action_needed'
        ? 'This Adventour is usable, but a few booking pieces still need attention.'
        : launchChecklist?.headline || 'Finish route setup before launching this Adventour.';
  const missingActions = missingInputs.map((missing) => ({
    id: `missing_${missing}`,
    label: `Add ${String(missing).replace(/_/g, ' ')}`,
    detail: 'Needed before Adventour can prepare reliable flight, stay, or date-specific booking steps.',
    status: 'action_needed',
  }));
  const nextActions = (bookingPlan?.next_best_actions || []).slice(0, 3).map((action) => ({
    id: `next_${action.type || action.label}`,
    label: action.label || 'Review booking step',
    detail: action.detail,
    status: 'action_needed',
  }));

  return {
    ...current,
    status,
    headline,
    can_start: canStart,
    booking_score: Number(bookingScore.toFixed(3)),
    currency: plan.price_breakdown?.currency || current?.currency || 'USD',
    party_size: plan.price_breakdown?.party_size || current?.party_size,
    known_per_person: {
      ...(current?.known_per_person || {}),
      low: knownLow ?? current?.known_per_person?.low,
      high: knownHigh ?? current?.known_per_person?.high,
      label: costLabel || null,
    },
    quote_plan: quotePlan,
    cost_confidence: {
      ...(current?.cost_confidence || {}),
      quote_status: quotePlan.status,
      quote_required_count: quotePlan.required_count || 0,
      quote_ready_count: quotePlan.ready_count || 0,
      quote_plan: quotePlan,
      message: current?.cost_confidence?.tracked_total
        ? current.cost_confidence.message
        : quotePlan.message || current?.cost_confidence?.message,
    },
    missing_inputs: missingInputs,
    quick_stats: [
      ...(betaReadiness ? [{
        id: 'beta_readiness',
        label: 'Beta ready',
        value: `${Math.round((betaReadiness.score || 0) * 100)}%`,
        status: betaReadiness.ready_for_friend_testing ? 'ready' : 'action_needed',
      }] : []),
      {
        id: 'known_cost',
        label: 'Known cost',
        value: costLabel || 'Manual pricing',
        status: costLabel ? 'ready' : 'manual',
      },
      {
        id: 'booking_links',
        label: 'Booking links',
        value: bookingLinks.length,
        status: bookingLinks.length ? 'ready' : 'manual',
      },
      {
        id: 'saveable_items',
        label: 'Saveable pieces',
        value: Math.max(saveableTimelineCount, savePrompts.length),
        status: savePrompts.length || saveableTimelineCount ? 'ready' : 'manual',
      },
      {
        id: 'event_reservations',
        label: 'Event RSVPs',
        value: eventReservationCount,
        status: eventReservationCount ? 'ready' : 'optional',
      },
      ...(current?.mobility_setup ? [{
        id: 'mobility',
        label: 'Mobility',
        value: current.mobility_setup.label || current.mobility_setup.provider_label || 'Manual',
        status: 'ready',
      }] : []),
      ...(bookingChecklist ? [{
        id: 'booking_checklist',
        label: 'Checklist',
        value: `${bookingChecklist.ready_count || 0}/${bookingChecklist.items?.length || 0} ready`,
        status: bookingChecklist.blocking_count ? 'action_needed' : 'ready',
      }] : []),
      ...((quotePlan.required_count || 0) > 0 ? [{
        id: 'travel_quotes',
        label: 'Travel quotes',
        value: `${quotePlan.ready_count || 0}/${quotePlan.required_count || 0} ready`,
        status: quotePlan.status === 'ready_to_quote' ? 'ready' : 'action_needed',
      }] : []),
      ...(authenticityPacket ? [{
        id: 'authenticity_packet',
        label: 'Local promise',
        value: `${authenticityPacket.local_feeling_count || 0}/${authenticityPacket.stop_count || 0} local`,
        status: authenticityPacket.status === 'ready' ? 'ready' : 'manual',
      }] : []),
      ...(friendTestPacket ? [{
        id: 'friend_test_packet',
        label: 'Friend test',
        value: friendTestPacket.friend_testable ? 'Ready' : String(friendTestPacket.status || 'watch').replace(/_/g, ' '),
        status: friendTestPacket.friend_testable ? 'ready' : 'manual',
      }] : []),
      ...(swapGuide ? [{
        id: 'swap_guide',
        label: 'Swap safety',
        value: `${swapGuide.swappable_stop_count || 0}/${swapGuide.stop_count || 0} stops`,
        status: swapGuide.status === 'ready' ? 'ready' : 'manual',
      }] : []),
      ...(routeModelConfidence ? [{
        id: 'route_model_confidence',
        label: 'Model signal',
        value: `${Math.round((routeModelConfidence.score || 0) * 100)}%`,
        status: routeModelConfidence.status === 'ready' ? 'ready' : 'manual',
      }] : []),
      ...(eventPacket ? [{
        id: 'event_packet',
        label: 'Event anchor',
        value: eventPacket.short_label || 'Scout',
        status: eventPacket.status === 'ready' ? 'ready' : 'manual',
      }] : []),
    ],
    required_actions: [...missingActions, ...nextActions].slice(0, 5),
    booking_links: bookingLinks,
    save_prompts: savePrompts,
    booking_checklist: bookingChecklist,
    authenticity_packet: authenticityPacket,
    event_packet: eventPacket,
    friend_test_packet: friendTestPacket,
    swap_guide: swapGuide,
    route_model_confidence: routeModelConfidence,
    beta_readiness: betaReadiness,
    next_step: (
      (bookingChecklist?.blocking_count ? bookingChecklist.next_action : undefined)
      || bookingChecklist?.next_action
      || missingActions[0]?.label
      || nextActions[0]?.label
      || current?.mobility_setup?.next_step
      || 'Open booking links and save confirmations in Adventour.'
    ),
    reservation_storage_ready: bookingPlan?.reservation_storage?.status === 'ready' || current?.reservation_storage_ready || false,
  };
};

const swapSummaryForItineraryPlan = (plan: ItineraryPlan): ItineraryPlan['swap_summary'] => {
  const swappedSlots = plan.days.flatMap((day) => (
    day.stops
      .filter((stop) => stop.swap_history?.swapped)
      .map((stop) => ({
        day: day.day,
        slot_id: stop.slot_id,
        slot_label: stop.label,
        from_place_id: stop.swap_history?.from_place_id,
        from_name: stop.swap_history?.from_name,
        to_place_id: stop.swap_history?.to_place_id,
        to_name: stop.swap_history?.to_name,
        swapped_at: stop.swap_history?.swapped_at,
        impact: stop.swap_history?.impact,
      }))
  ));

  return {
    swapped_stop_count: swappedSlots.length,
    swapped_slots: swappedSlots,
  };
};

const withSwapSummary = (plan: ItineraryPlan): ItineraryPlan => ({
  ...plan,
  swap_summary: swapSummaryForItineraryPlan(plan),
});

const finalizedItineraryPlan = (plan: ItineraryPlan): ItineraryPlan => {
  const nextPlan: ItineraryPlan = {
    ...plan,
    days: plan.days.map((day) => ({
      ...day,
      stops: day.stops.map((stop) => ({
        ...stop,
        alternatives: [...(stop.alternatives || [])],
      })),
    })),
  };

  nextPlan.price_breakdown = priceEstimateForItineraryPlan(nextPlan);
  nextPlan.local_events = localEventsForItineraryPlan(nextPlan);
  nextPlan.route_authenticity = routeAuthenticityForItineraryPlan(nextPlan);
  nextPlan.route_readiness = routeReadinessForItineraryPlan(nextPlan);
  nextPlan.route_explanation = routeExplanationForItineraryPlan(nextPlan);
  nextPlan.launch_checklist = launchChecklistForItineraryPlan(nextPlan);
  nextPlan.scenario_readiness = scenarioReadinessForItineraryPlan(nextPlan);
  nextPlan.itinerary_story = itineraryStoryForItineraryPlan(nextPlan);
  nextPlan.swap_guide = swapGuideForItineraryPlan(nextPlan);
  nextPlan.route_model_confidence = routeModelConfidenceForItineraryPlan(nextPlan);
  nextPlan.trip_packet = tripPacketForItineraryPlan(nextPlan);

  return withSwapSummary(nextPlan);
};

const describeAxiosError = (error: unknown) => {
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

const emptyMessageFromFilterSummary = (filterSummary: any, fallback: string) => {
  if (!filterSummary) {
    return fallback;
  }

  const skipped = filterSummary.skipped || {};
  const hardSkipped = skipped.hard_constraints || 0;
  const rawCandidates = filterSummary.raw_candidates || 0;
  if (filterSummary.hard_constraints_active && rawCandidates > 0 && hardSkipped >= rawCandidates) {
    return 'Your Skip this trip filters removed every nearby option. Clear one skip or widen the search distance.';
  }
  if (filterSummary.hard_constraints_active && hardSkipped > 0) {
    return 'No places matched after your Skip this trip filters. Clear one skip or try another scout style.';
  }
  if ((skipped.distance || 0) > 0 && rawCandidates > 0) {
    return 'Nearby options were outside your search distance. Try Explore or Wide.';
  }
  if ((skipped.decided || 0) > 0 && rawCandidates > 0) {
    return 'You have already accepted or passed on the nearby options. Refresh, widen the search, or clear skips.';
  }
  return fallback;
};

const plannedStopCount = (plan: ItineraryPlan | null) =>
  plan?.days.reduce((total, day) => total + day.stops.length, 0) ?? 0;

const itineraryStopSwapKey = (dayIndex: number, stopIndex: number, stop?: ItineraryStop) =>
  `${dayIndex}-${stopIndex}-${stop?.slot_id || 'slot'}`;

const itineraryDiagnosticFromFilterSummary = (plan: ItineraryPlan | null) => {
  if (!plan) {
    return null;
  }

  const summary = plan.filter_summary;
  const skipped = summary?.skipped || {};
  const stops = plannedStopCount(plan);
  const hardSkipped = skipped.hard_constraints || 0;
  const rawCandidates = summary?.raw_candidates || 0;

  if (stops === 0 && summary?.hard_constraints_active && rawCandidates > 0 && hardSkipped >= rawCandidates) {
    return {
      title: 'No route with these skips',
      message: 'Your Skip this trip filters removed every route candidate. Clear one skip, widen the range, or try another scout style.',
    };
  }

  if (stops === 0 && summary?.hard_constraints_active && hardSkipped > 0) {
    return {
      title: 'Route filtered down too far',
      message: 'Adventour found candidates, but your skip filters removed the ones that fit this route.',
    };
  }

  if (stops === 0 && (skipped.distance || 0) > 0) {
    return {
      title: 'Route needs a wider range',
      message: 'The strongest candidates were outside your search distance. Try Explore or Wide and rebuild the route.',
    };
  }

  if (stops === 0 && (skipped.decided || 0) > 0) {
    return {
      title: 'Basket already explored',
      message: 'You have already accepted or passed on the nearby options. Refresh the basket or widen the range.',
    };
  }

  if (stops === 0) {
    return {
      title: 'Route not ready yet',
      message: 'Adventour could not assemble stops from this launch point yet. Try a broader range or a different scout style.',
    };
  }

  if (summary?.hard_constraints_active && hardSkipped > 0) {
    return {
      title: 'Skips shaped this route',
      message: `${hardSkipped} candidate${hardSkipped === 1 ? '' : 's'} stayed out of this plan because of your Skip this trip filters.`,
    };
  }

  return null;
};

const swapImpactSummary = (alternative: ItineraryRecommendation) => {
  const impact = alternative.swap_impact;
  if (!impact) {
    return 'Tap to rebalance this stop.';
  }

  const reasons = impact.reasons?.filter(Boolean) || [];
  const readinessLabel = impact.swap_readiness?.label;
  const delta = impact.route_score_delta || 0;
  const scoreLabel = delta >= 0.05
    ? 'stronger route fit'
    : delta <= -0.15
      ? 'bolder route change'
      : 'similar route fit';
  const reasonText = reasons.slice(0, 2).join(' + ');
  if (readinessLabel && reasonText) {
    return `${readinessLabel}: ${reasonText}`;
  }
  return readinessLabel || (reasons.length ? `${reasonText} - ${scoreLabel}` : scoreLabel);
};

const swapDecisionForAlternative = (alternative: ItineraryRecommendation) => {
  const impact = alternative.swap_impact;
  if (!impact) {
    return null;
  }
  if (impact.swap_decision) {
    return impact.swap_decision;
  }

  const status = impact.swap_readiness?.status;
  const routeDelta = impact.route_score_delta || 0;
  const travelDelta = impact.travel_efficiency_delta || 0;
  const partyDelta = Math.max(impact.member_fit_delta || 0, impact.member_rebalance_delta || 0);
  const consensusDelta = Math.max(impact.group_consensus_delta || 0, impact.group_consensus_gap_delta || 0);
  const consensusDeltaLabel = formatSignedDeltaPercent(consensusDelta);
  const authenticityDelta = impact.authenticity_delta || 0;
  const costStatus = impact.cost_impact_status;
  const costDetail = impact.cost_impact_detail;
  const lowFrictionScore = impact.low_friction_score ?? impact.swap_readiness?.low_friction_score;
  const lowFrictionLabel = impact.low_friction_label || impact.swap_readiness?.low_friction_label;
  const frictionReady = typeof lowFrictionScore === 'number' ? lowFrictionScore >= 0.5 : true;
  const shouldSwap = (
    ((status === 'safe_upgrade' || status === 'party_rebalance') && frictionReady)
    || (status === 'balanced_tradeoff' && routeDelta >= -0.08)
    || (consensusDelta >= 0.06 && routeDelta >= -0.12 && frictionReady)
  );
  const tradeoffs = [
    routeDelta < -0.08 ? 'lower route fit' : null,
    travelDelta < -0.08 ? 'more travel friction' : null,
    partyDelta < -0.05 ? 'weaker party fit' : null,
    Math.min(impact.group_consensus_delta || 0, impact.group_consensus_gap_delta || 0) < -0.04 ? 'weaker group balance' : null,
    authenticityDelta < -0.05 ? 'less local-authentic' : null,
    costStatus === 'pricier' ? `higher estimated cost${costDetail ? ` (${costDetail})` : ''}` : null,
  ].filter((item): item is string => Boolean(item));
  const balanceBestWhen = consensusDelta >= 0.06
    ? `Best when the route average looks fine but one traveler needs a fairer stop${consensusDeltaLabel ? ` (${consensusDeltaLabel} balance)` : ''}.`
    : undefined;

  return {
    headline: consensusDelta >= 0.06 ? 'Group balance boost' : impact.swap_readiness?.label || (shouldSwap ? 'Worth a look.' : 'Preview first.'),
    should_swap: shouldSwap,
    best_when: balanceBestWhen || impact.swap_readiness?.next_action || 'Choose this if it better matches the Adventour you want.',
    tradeoff: tradeoffs.length ? `Tradeoff: ${tradeoffs.slice(0, 3).join(', ')}.` : 'No major tradeoff detected.',
    primary_reason: impact.reasons?.[0],
    confidence: impact.swap_readiness?.score,
    low_friction_score: lowFrictionScore,
    low_friction_label: lowFrictionLabel,
    badges: [
      {
        label: 'Route',
        detail: routeDelta >= 0.04 ? 'upgrade' : routeDelta <= -0.08 ? 'risk' : 'similar',
        tone: routeDelta >= 0.04 ? 'positive' : routeDelta <= -0.08 ? 'caution' : 'neutral',
      },
      ...(costStatus === 'saves' ? [{ label: 'Cost', detail: costDetail || 'saves', tone: 'positive' }] : []),
      ...(costStatus === 'pricier' ? [{ label: 'Cost', detail: costDetail || 'higher', tone: 'caution' }] : []),
      ...(consensusDelta >= 0.04 ? [{ label: 'Balance', detail: consensusDeltaLabel || 'better', tone: 'positive' }] : []),
      ...(partyDelta >= 0.05 ? [{ label: 'Party', detail: 'better', tone: 'positive' }] : []),
      ...(typeof lowFrictionScore === 'number' && lowFrictionScore >= 0.78 ? [{ label: 'Friction', detail: 'low', tone: 'positive' }] : []),
      ...(typeof lowFrictionScore === 'number' && lowFrictionScore < 0.58 ? [{ label: 'Friction', detail: 'check', tone: 'caution' }] : []),
      ...(travelDelta <= -0.08 ? [{ label: 'Travel', detail: 'farther', tone: 'caution' }] : []),
      ...(authenticityDelta >= 0.05 ? [{ label: 'Local', detail: 'better', tone: 'positive' }] : []),
    ],
  };
};

const optionalNumber = (value: unknown, fallback = 0) => {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
};

const formatSignedDeltaPercent = (value?: number | null) => {
  if (value === undefined || value === null || !Number.isFinite(Number(value))) {
    return null;
  }
  const rounded = Math.round(Number(value) * 100);
  return `${rounded >= 0 ? '+' : ''}${rounded}%`;
};

const swapGuideForItineraryPlan = (plan: ItineraryPlan): SwapGuide | undefined => {
  const current = plan.swap_guide || plan.trip_packet?.swap_guide;
  const stops = plan.days.flatMap((day) => day.stops.map((stop) => ({ day, stop })));
  if (!stops.length) {
    return current || {
      status: 'needs_route',
      headline: 'Build a route before Adventour can suggest safe swaps.',
      next_action: 'Plan an Adventour first, then compare alternatives for each stop.',
      stop_count: 0,
      swappable_stop_count: 0,
      swap_coverage: 0,
      alternative_count: 0,
      recommended_swap_count: 0,
      low_friction_count: 0,
      authenticity_upgrade_count: 0,
      party_upgrade_count: 0,
      route_risk_count: 0,
      best_swaps: [],
    };
  }

  const alternatives = stops.flatMap(({ day, stop }) => (
    (stop.alternatives || []).map((alternative) => {
      const impact = alternative.swap_impact || {};
      const decision = swapDecisionForAlternative(alternative) || impact.swap_decision || {};
      const readiness = impact.swap_readiness || {};
      return {
        day: day.day,
        slot_id: stop.slot_id,
        slot_label: stop.label,
        from_place_id: stop.recommendation.place_id,
        from_name: stop.recommendation.name || stop.recommendation.display?.name || 'current stop',
        to_place_id: alternative.place_id,
        to_name: alternative.name || alternative.display?.name || 'swap option',
        headline: decision.headline || readiness.label,
        best_when: decision.best_when || readiness.next_action,
        tradeoff: decision.tradeoff,
        should_swap: Boolean(decision.should_swap),
        confidence: decision.confidence ?? readiness.score ?? null,
        low_friction_score: impact.low_friction_score ?? readiness.low_friction_score ?? null,
        low_friction_label: impact.low_friction_label || readiness.low_friction_label,
        route_score_delta: impact.route_score_delta ?? null,
        authenticity_delta: impact.authenticity_delta ?? null,
        member_fit_delta: impact.member_fit_delta ?? null,
        member_rebalance_delta: impact.member_rebalance_delta ?? null,
        group_consensus_delta: impact.group_consensus_delta ?? null,
        group_consensus_gap_delta: impact.group_consensus_gap_delta ?? null,
        target_members: impact.target_members || [],
        weakened_members: impact.weakened_members || [],
        travel_efficiency_delta: impact.travel_efficiency_delta ?? null,
        travel_distance_meters: impact.travel_distance_meters ?? null,
        price_level_delta: impact.price_level_delta ?? null,
        known_cost_delta_low: impact.known_cost_delta_low ?? null,
        known_cost_delta_high: impact.known_cost_delta_high ?? null,
        cost_impact_status: impact.cost_impact_status ?? null,
        cost_impact_label: impact.cost_impact_label ?? null,
        cost_impact_detail: impact.cost_impact_detail ?? null,
        status: readiness.status,
        reasons: impact.reasons || [],
        badges: decision.badges || [],
      };
    })
  ));
  const stopCount = stops.length;
  const swappableStopCount = stops.filter(({ stop }) => (stop.alternatives || []).length > 0).length;
  const recommendedSwaps = alternatives.filter((item) => item.should_swap);
  const lowFrictionSwaps = alternatives.filter((item) => optionalNumber(item.low_friction_score) >= 0.78);
  const authenticityUpgrades = alternatives.filter((item) => optionalNumber(item.authenticity_delta) >= 0.05);
  const partyUpgrades = alternatives.filter((item) => Math.max(optionalNumber(item.member_fit_delta), optionalNumber(item.member_rebalance_delta)) >= 0.05);
  const consensusUpgrades = alternatives.filter((item) => (
    Math.max(optionalNumber(item.group_consensus_delta), optionalNumber(item.group_consensus_gap_delta)) >= 0.04
  ));
  const routeRisks = alternatives.filter((item) => item.status === 'route_risk' || optionalNumber(item.travel_efficiency_delta) <= -0.12);
  const costCautions = alternatives.filter((item) => item.cost_impact_status === 'pricier');
  const costSavings = alternatives.filter((item) => item.cost_impact_status === 'saves');
  const swapCoverage = swappableStopCount / Math.max(1, stopCount);
  const bestSwaps = [...alternatives].sort((a, b) => (
    Number(b.should_swap) - Number(a.should_swap)
    || optionalNumber(b.confidence) - optionalNumber(a.confidence)
    || Math.max(optionalNumber(b.group_consensus_delta), optionalNumber(b.group_consensus_gap_delta))
      - Math.max(optionalNumber(a.group_consensus_delta), optionalNumber(a.group_consensus_gap_delta))
    || optionalNumber(b.low_friction_score) - optionalNumber(a.low_friction_score)
    || Number(b.cost_impact_status === 'saves') - Number(a.cost_impact_status === 'saves')
    || optionalNumber(b.member_rebalance_delta) - optionalNumber(a.member_rebalance_delta)
    || optionalNumber(b.authenticity_delta) - optionalNumber(a.authenticity_delta)
    || optionalNumber(b.route_score_delta) - optionalNumber(a.route_score_delta)
  )).slice(0, 4);

  let status: SwapGuide['status'];
  let headline: string;
  let nextAction: string;
  if (swapCoverage >= 0.8 && recommendedSwaps.length) {
    status = 'ready';
    headline = 'This route is flexible enough to customize.';
    nextAction = 'Use the highlighted swaps when a stop does not fit the group or vibe.';
  } else if (swapCoverage >= 0.5) {
    status = 'watch';
    headline = 'This route has some flexibility, but not every stop has a strong swap.';
    nextAction = 'Rebuild or widen the range if you want more swap safety before sharing.';
  } else {
    status = 'needs_attention';
    headline = 'This route may feel brittle if someone dislikes a stop.';
    nextAction = 'Compare scout styles or widen the search to add more alternatives.';
  }
  if (consensusUpgrades.length) {
    nextAction = 'Use group-balance swaps when one friend is quietly getting a weaker route.';
  } else if (partyUpgrades.length) {
    nextAction = 'Use party-friendly swaps when a friend looks underserved.';
  } else if (authenticityUpgrades.length) {
    nextAction = 'Swap in a local-feeling alternative if the route starts feeling too generic.';
  }

  return {
    ...current,
    status,
    headline,
    next_action: nextAction,
    stop_count: stopCount,
    swappable_stop_count: swappableStopCount,
    swap_coverage: Number(swapCoverage.toFixed(3)),
    alternative_count: alternatives.length,
    recommended_swap_count: recommendedSwaps.length,
    low_friction_count: lowFrictionSwaps.length,
    authenticity_upgrade_count: authenticityUpgrades.length,
    party_upgrade_count: partyUpgrades.length,
    consensus_upgrade_count: consensusUpgrades.length,
    route_risk_count: routeRisks.length,
    cost_caution_count: costCautions.length,
    cost_saving_count: costSavings.length,
    best_swaps: bestSwaps,
  };
};

const localEventSourceSummary = (plan: ItineraryPlan | null) => {
  const summary = plan?.local_events?.summary?.source_summary;
  if (!summary) {
    return null;
  }

  const badges = summary.source_badges?.length
    ? summary.source_badges
    : Object.entries(summary.source_mix || {}).map(([kind, count]) => ({
      kind,
      badge: kind.replace(/_/g, ' '),
      count,
    }));

  return {
    ...summary,
    badges,
  };
};

const socialReadinessForLocalEvents = (
  events: LocalEventRecommendation[],
  current?: LocalEventSocialReadiness,
): LocalEventSocialReadiness => {
  const eventCount = events.length;
  const friendGoing = events.reduce((total, event) => total + (event.social?.friend_going_count || 0), 0);
  const friendInterested = events.reduce((total, event) => total + (event.social?.friend_interested_count || 0), 0);
  const going = events.reduce((total, event) => total + (event.social?.going_count || 0), 0);
  const interested = events.reduce((total, event) => total + (event.social?.interested_count || 0), 0);
  const friendSignal = friendGoing + friendInterested;
  const communitySignal = going + interested;
  const reservationReady = events.reduce((total, event) => total + (event.reservation_url ? 1 : 0), 0);
  const socialAnchorCount = events.reduce((total, event) => {
    const eventFriendSignal = (event.social?.friend_going_count || 0) + (event.social?.friend_interested_count || 0);
    const eventCommunitySignal = (event.social?.going_count || 0) + (event.social?.interested_count || 0);
    return total + (eventFriendSignal || eventCommunitySignal || event.event_story?.social_ready ? 1 : 0);
  }, 0);
  const topSocialEvent = events.find((event) => (
    (event.social?.friend_going_count || 0)
    + (event.social?.friend_interested_count || 0)
    + (event.social?.going_count || 0)
    + (event.social?.interested_count || 0)
  ) > 0);

  const score = eventCount
    ? Math.min(1, Number((
      Math.min(1, friendSignal / eventCount) * 0.42
      + Math.min(1, communitySignal / eventCount) * 0.28
      + Math.min(1, socialAnchorCount / eventCount) * 0.18
      + Math.min(1, reservationReady / eventCount) * 0.12
    ).toFixed(3)))
    : 0;
  const meetupReady = Boolean(friendSignal || (communitySignal && reservationReady));
  const status = meetupReady
    ? 'ready'
    : communitySignal || socialAnchorCount
      ? 'watch'
      : eventCount
        ? 'needs_signal'
        : 'needs_scouting';
  const headline = friendSignal
    ? `${friendSignal} friend signal${friendSignal === 1 ? '' : 's'} on local events.`
    : communitySignal
      ? `${communitySignal} Adventourer signal${communitySignal === 1 ? '' : 's'} on local events.`
      : eventCount
        ? 'Local events are present, but need social signal.'
        : 'No local events are ready yet.';
  const nextAction = meetupReady
    ? 'Use this event as a social anchor or RSVP before launch.'
    : eventCount
      ? 'Ask friends to mark Interested/Going or add a stronger community event.'
      : 'Scout or add a local event before relying on this route socially.';

  return {
    ...(current || {}),
    status,
    headline,
    score,
    event_count: eventCount,
    friend_signal_count: friendSignal,
    community_signal_count: communitySignal,
    friend_going_count: friendGoing,
    friend_interested_count: friendInterested,
    going_count: going,
    interested_count: interested,
    social_anchor_count: socialAnchorCount,
    reservation_ready_count: reservationReady,
    meetup_ready: meetupReady,
    top_social_event: topSocialEvent ? {
      id: topSocialEvent.id,
      title: topSocialEvent.title,
      reservation_url: topSocialEvent.reservation_url || null,
      source_url: topSocialEvent.source_url || null,
    } : current?.top_social_event || null,
    next_action: nextAction,
    meetup_checklist: current?.meetup_checklist,
    blocking_count: current?.blocking_count,
  };
};

const localEventSocialSummary = (plan: ItineraryPlan | null) => {
  const summary = plan?.local_events?.summary;
  if (!summary) {
    return null;
  }

  const readiness = summary.social_readiness;
  const friendGoing = summary.friend_going_count || 0;
  const friendInterested = summary.friend_interested_count || 0;
  const communityGoing = summary.going_count || 0;
  const communityInterested = summary.interested_count || 0;
  const eventCount = summary.event_count || 0;
  const reservationReady = summary.reservation_ready_count || 0;
  const friendSignal = friendGoing + friendInterested;
  const communitySignal = communityGoing + communityInterested;

  const headline = readiness?.headline || (friendSignal
    ? `${friendSignal} friend signal${friendSignal === 1 ? '' : 's'} on this trip`
    : communitySignal
      ? `${communitySignal} Adventourer signal${communitySignal === 1 ? '' : 's'} nearby`
      : eventCount
        ? 'No friend signals yet'
        : 'No local event signals yet');

  return {
    headline,
    status: readiness?.status,
    score: readiness?.score,
    nextAction: readiness?.next_action,
    topSocialEvent: readiness?.top_social_event,
    friendGoing: readiness?.friend_going_count ?? friendGoing,
    friendInterested: readiness?.friend_interested_count ?? friendInterested,
    communityGoing: readiness?.going_count ?? communityGoing,
    communityInterested: readiness?.interested_count ?? communityInterested,
    eventCount: readiness?.event_count ?? eventCount,
    reservationReady: readiness?.reservation_ready_count ?? reservationReady,
    friendSignal: readiness?.friend_signal_count ?? friendSignal,
    communitySignal: readiness?.community_signal_count ?? communitySignal,
    socialAnchorCount: readiness?.social_anchor_count ?? summary.social_anchor_count ?? 0,
    meetupReady: Boolean(readiness?.meetup_ready),
    checklist: readiness?.meetup_checklist || [],
    blockingCount: readiness?.blocking_count || 0,
    hasSocialSignal: Boolean(readiness?.friend_signal_count || readiness?.community_signal_count || friendSignal > 0 || communitySignal > 0),
  };
};

const eventPlanStatusLabel = (status?: string) => {
  switch (status) {
    case 'ready':
      return 'Ready';
    case 'needs_confirmation':
      return 'Confirm';
    case 'needs_scouting':
      return 'Scout';
    default:
      return 'Plan';
  }
};

const eventPlanItemStatusLabel = (status?: string) => {
  switch (status) {
    case 'ready':
      return 'Ready';
    case 'research':
      return 'Check';
    case 'social':
      return 'Friends';
    case 'manual':
      return 'Manual';
    case 'optional':
      return 'Optional';
    default:
      return status || 'Open';
  }
};

const localEventReadinessLabel = (status?: string) => {
  switch (status) {
    case 'ready':
      return 'Ready to save';
    case 'needs_confirmation':
      return 'Confirm details';
    case 'research':
      return 'Needs scouting';
    default:
      return status ? status.replace(/_/g, ' ') : 'Checking';
  }
};

const localEventFreshnessCheck = (event: LocalEventRecommendation) =>
  event.event_readiness?.checks?.find((check) => check.name === 'freshness');

const localEventFreshnessStatus = (event: LocalEventRecommendation) => {
  const check = localEventFreshnessCheck(event);
  if (check?.status) {
    return check.status;
  }

  const freshness = event.score_components?.source_freshness;
  if (typeof freshness !== 'number') {
    return null;
  }

  if (freshness >= 0.75) {
    return 'pass';
  }
  if (freshness >= 0.5) {
    return 'warn';
  }
  return 'fail';
};

const localEventFreshnessLabel = (event: LocalEventRecommendation) => {
  const status = localEventFreshnessStatus(event);
  if (!status) {
    return null;
  }

  switch (status) {
    case 'pass':
      return 'Current source';
    case 'warn':
    case 'watch':
      return 'Confirm date';
    case 'fail':
      return 'Needs source';
    default:
      return 'Check source';
  }
};

const localEventFreshnessAction = (event: LocalEventRecommendation) => {
  const check = localEventFreshnessCheck(event);
  const status = localEventFreshnessStatus(event);
  if (!status || status === 'pass') {
    return null;
  }
  return check?.action || 'Confirm the event date and details before relying on it.';
};

const eventSourceTypeLabel = (sourceType?: string) => {
  switch (sourceType) {
    case 'adventour':
      return 'Adventour';
    case 'local_search':
      return 'Local calendars';
    case 'official_search':
      return 'Official';
    case 'market_popup_search':
      return 'Markets';
    case 'event_platform_search':
      return 'Platforms';
    case 'community_search':
      return 'Social';
    default:
      return 'Source';
  }
};

const bookingComponentReservationTypes = (component: BookingComponent) => {
  if (component.type === 'event_or_place') {
    return ['place', 'event'];
  }
  return [component.type];
};

const bookingComponentNeedsReservation = (component: BookingComponent) => (
  Boolean(component.stores_reservation)
  && component.status !== 'not_needed_for_day_trip'
  && component.status !== 'optional_for_day_trip'
);

const bookingComponentLabel = (component: BookingComponent) => {
  if (component.type === 'local_transport') {
    return 'Local travel';
  }
  if (component.type === 'event_or_place') {
    return 'Tickets/events';
  }
  return component.label;
};

const RESERVATION_TYPES_ADDED_TO_ESTIMATE = new Set(['flight', 'stay', 'event']);

const reservationCostImpact = (reservations: TravelReservation[]): ReservationCostImpact => {
  const impact = reservations.reduce<ReservationCostImpact>((current, reservation) => {
    const cost = typeof reservation.cost_total === 'number' ? reservation.cost_total : 0;
    if (cost <= 0) {
      return current;
    }
    const next = {
      ...current,
      tracked_total: current.tracked_total + cost,
    };
    if (RESERVATION_TYPES_ADDED_TO_ESTIMATE.has(reservation.reservation_type)) {
      return {
        ...next,
        estimate_add_on_total: next.estimate_add_on_total + cost,
        estimate_add_on_types: current.estimate_add_on_types.includes(reservation.reservation_type)
          ? current.estimate_add_on_types
          : [...current.estimate_add_on_types, reservation.reservation_type],
      };
    }
    return next;
  }, {
    tracked_total: 0,
    estimate_add_on_total: 0,
    estimate_add_on_types: [],
  });

  return {
    ...impact,
    tracked_total: Number(impact.tracked_total.toFixed(2)),
    estimate_add_on_total: Number(impact.estimate_add_on_total.toFixed(2)),
  };
};

const bookingCoverageForPlan = (
  components: BookingComponent[],
  reservations: TravelReservation[],
) => {
  const items = components
    .filter(bookingComponentNeedsReservation)
    .map((component) => {
      const reservationTypes = bookingComponentReservationTypes(component);
      const matchingReservations = reservations.filter((reservation) => (
        reservationTypes.includes(reservation.reservation_type)
      ));
      const confirmedCount = matchingReservations.filter((reservation) => (
        Boolean(reservation.confirmation_code || reservation.booking_url || reservation.cost_total)
      )).length;
      return {
        id: component.id,
        label: bookingComponentLabel(component),
        status: matchingReservations.length ? 'saved' : 'missing',
        savedCount: matchingReservations.length,
        confirmedCount,
        component,
      };
    });

  const savedCount = items.filter((item) => item.status === 'saved').length;
  const confirmedCount = items.filter((item) => item.confirmedCount > 0).length;
  const missingLabels = items
    .filter((item) => item.status === 'missing')
    .map((item) => item.label);

  return {
    items,
    savedCount,
    confirmedCount,
    missingLabels,
  };
};

type BookingCoverageItem = ReturnType<typeof bookingCoverageForPlan>['items'][number];

const reservationTypeForCoverageItem = (item: BookingCoverageItem) => {
  const reservationTypes = bookingComponentReservationTypes(item.component);
  if (reservationTypes.includes('event')) {
    return 'event';
  }
  return reservationTypes[0] || 'other';
};

const commandCenterWithReservationCoverage = (
  commandCenter: TripPacket['booking_command_center'],
  missingItems: BookingCoverageItem[],
): TripPacket['booking_command_center'] => {
  const existingCommands = (commandCenter?.commands || []).filter((command) => (
    !String(command.id || '').startsWith('missing_booking_')
  ));
  const reservationCommands = missingItems.map((item, index) => ({
    id: `missing_booking_${item.id || index + 1}`,
    phase: 'save',
    label: `Save ${item.label}`,
    detail: 'Add the confirmation, booking link, or cost so this Adventour can travel with the details.',
    status: 'action_needed',
    action: 'Save booking details in Adventour',
    component_type: item.id || 'reservation',
    reservation_type: reservationTypeForCoverageItem(item),
    provider_label: null,
    source_url: null,
    priority: 2 + index,
    can_open: false,
    can_save: true,
  }));

  if (!reservationCommands.length && !commandCenter) {
    return commandCenter;
  }

  const commands = [...reservationCommands, ...existingCommands];
  const visibleCommands = commands.slice(0, 6);
  const primaryAction = visibleCommands[0] || null;
  const readyCount = visibleCommands.filter((command) => command.status === 'ready').length;
  const actionNeededCount = visibleCommands.filter((command) => command.status === 'action_needed').length;
  const openLinkCount = visibleCommands.filter((command) => command.can_open).length;
  const savePromptCount = visibleCommands.filter((command) => command.can_save).length;
  const status = reservationCommands.length ? 'action_needed' : commandCenter?.status || 'manual';

  return {
    ...(commandCenter || {}),
    status,
    headline: reservationCommands.length && primaryAction
      ? `Next best move: ${primaryAction.label}.`
      : commandCenter?.headline,
    primary_action: primaryAction,
    commands: visibleCommands,
    command_count: commands.length,
    ready_count: readyCount,
    action_needed_count: actionNeededCount,
    open_link_count: openLinkCount,
    save_prompt_count: savePromptCount,
  };
};

const withReservationCoverage = (
  plan: ItineraryPlan,
  reservations: TravelReservation[],
): ItineraryPlan => {
  const components = plan.booking_plan?.components || [];
  const tripPacket = plan.trip_packet;
  if (!tripPacket || !components.length) {
    return plan;
  }

  const coverage = bookingCoverageForPlan(components, reservations);
  if (!coverage.items.length) {
    return plan;
  }

  const missingItems = coverage.items.filter((item) => item.status === 'missing');
  const savedItems = coverage.items.filter((item) => item.status === 'saved');
  const costImpact = reservationCostImpact(reservations);
  const partySize = Math.max(1, tripPacket.party_size || plan.price_breakdown?.party_size || 1);
  const estimateAddOnPerPerson = costImpact.estimate_add_on_total / partySize;
  const knownLow = tripPacket.known_per_person?.low;
  const knownHigh = tripPacket.known_per_person?.high;
  const combinedKnownLow = typeof knownLow === 'number'
    ? Number((knownLow + estimateAddOnPerPerson).toFixed(2))
    : null;
  const combinedKnownHigh = typeof knownHigh === 'number'
    ? Number((knownHigh + estimateAddOnPerPerson).toFixed(2))
    : null;
  const currency = tripPacket.currency || plan.price_breakdown?.currency || 'USD';
  const combinedLabel = combinedKnownLow != null && combinedKnownHigh != null
    ? `$${combinedKnownLow}-${combinedKnownHigh} known per person`
    : tripPacket.known_per_person?.label || null;
  const savedDetailStat = {
    id: 'saved_reservations',
    label: 'Saved details',
    value: `${coverage.savedCount}/${coverage.items.length}`,
    status: missingItems.length ? 'manual' : 'ready',
  };
  const confirmedDetailStat = {
    id: 'confirmed_reservations',
    label: 'Confirmed',
    value: coverage.confirmedCount,
    status: coverage.confirmedCount >= savedItems.length && savedItems.length ? 'ready' : 'manual',
  };
  const savedCostStat = costImpact.tracked_total > 0 ? {
    id: 'saved_cost',
    label: 'Saved cost',
    value: `$${costImpact.tracked_total.toFixed(2)}`,
    status: costImpact.estimate_add_on_total > 0 ? 'ready' : 'manual',
  } : null;
  const reservationActions = missingItems.map((item) => ({
    id: `missing_booking_${item.id}`,
    label: `Save ${item.label}`,
    detail: 'Add the confirmation, booking link, or cost so this Adventour can travel with the details.',
    status: 'action_needed',
  }));
  const existingActions = (tripPacket.required_actions || []).filter((action) => (
    !String(action.id || '').startsWith('missing_booking_')
  ));
  const existingStats = (tripPacket.quick_stats || []).filter((stat) => (
    stat.id !== 'saved_reservations' && stat.id !== 'confirmed_reservations' && stat.id !== 'saved_cost'
  ));
  const currentChecklist = tripPacket.booking_checklist;
  const confirmationChecklistItem: NonNullable<BookingChecklist['items']>[number] = {
    id: 'saved_confirmations',
    label: 'Saved confirmations',
    status: missingItems.length ? 'action_needed' : 'ready',
    detail: missingItems.length
      ? `${coverage.savedCount}/${coverage.items.length} trip pieces saved. Missing ${coverage.missingLabels.slice(0, 3).join(', ')}.`
      : `${coverage.savedCount}/${coverage.items.length} trip pieces saved for this Adventour.`,
    action: missingItems.length
      ? `Save ${missingItems[0].label} details before launch.`
      : 'Review saved booking details, then launch this Adventour.',
    blocking: false,
    required_count: coverage.items.length,
    saved_count: coverage.savedCount,
    confirmed_count: coverage.confirmedCount,
    missing_labels: coverage.missingLabels,
  };
  const checklistItems = currentChecklist?.items?.filter((item) => item.id !== 'saved_confirmations') || [];
  const reservationWalletIndex = checklistItems.findIndex((item) => item.id === 'reservation_wallet');
  const nextChecklistItems = [...checklistItems];
  if (reservationWalletIndex >= 0) {
    nextChecklistItems.splice(reservationWalletIndex + 1, 0, confirmationChecklistItem);
  } else {
    nextChecklistItems.push(confirmationChecklistItem);
  }
  const checklistReadyCount = nextChecklistItems.filter((item) => item.status === 'ready').length;
  const checklistActionCount = nextChecklistItems.filter((item) => (
    item.status === 'action_needed' || item.status === 'manual'
  )).length;
  const checklistBlockingCount = nextChecklistItems.filter((item) => item.blocking).length;
  const nextChecklist = currentChecklist ? {
    ...currentChecklist,
    status: checklistBlockingCount
      ? 'needs_details'
      : checklistActionCount
        ? 'ready_with_manual_steps'
        : 'ready',
    headline: missingItems.length
      ? 'Save missing confirmations before this packet feels complete.'
      : currentChecklist.headline || 'Booking, saving, and local setup are ready.',
    ready_count: checklistReadyCount,
    action_count: checklistActionCount,
    blocking_count: checklistBlockingCount,
    next_action: missingItems.length ? confirmationChecklistItem.action : currentChecklist.next_action,
    items: nextChecklistItems,
  } : undefined;
  const bookingCommandCenter = commandCenterWithReservationCoverage(
    tripPacket.booking_command_center,
    missingItems,
  );
  const primaryCommandLabel = bookingCommandCenter?.primary_action?.label;
  const nextStep = missingItems.length
    ? primaryCommandLabel || `Save ${missingItems[0].label} details before launch.`
    : tripPacket.next_step || 'Review saved booking details, then launch this Adventour.';
  const status = tripPacket.status === 'blocked'
    ? tripPacket.status
    : missingItems.length
      ? 'action_needed'
      : tripPacket.status === 'needs_details'
        ? tripPacket.status
        : 'ready';
  const headline = missingItems.length
    ? 'Save booking details so this Adventour can travel with confirmations.'
    : tripPacket.headline || 'Saved booking details are attached to this Adventour packet.';

  return {
    ...plan,
    trip_packet: {
      ...tripPacket,
      status,
      headline,
      reservation_coverage: {
        required_count: coverage.items.length,
        saved_count: coverage.savedCount,
        confirmed_count: coverage.confirmedCount,
        missing_labels: coverage.missingLabels,
      },
      cost_confidence: {
        status: costImpact.estimate_add_on_total > 0
          ? (missingItems.length ? 'partially_saved' : 'saved')
          : 'estimated',
        tracked_total: costImpact.tracked_total,
        estimate_add_on_total: costImpact.estimate_add_on_total,
        estimate_add_on_per_person: Number(estimateAddOnPerPerson.toFixed(2)),
        combined_known_low: combinedKnownLow,
        combined_known_high: combinedKnownHigh,
        combined_label: combinedLabel,
        currency,
        add_on_types: costImpact.estimate_add_on_types,
        unknown_types: tripPacket.cost_confidence?.unknown_types,
        quote_status: tripPacket.cost_confidence?.quote_status || tripPacket.quote_plan?.status,
        quote_required_count: tripPacket.cost_confidence?.quote_required_count || tripPacket.quote_plan?.required_count || 0,
        quote_ready_count: tripPacket.cost_confidence?.quote_ready_count || tripPacket.quote_plan?.ready_count || 0,
        quote_plan: tripPacket.cost_confidence?.quote_plan || tripPacket.quote_plan,
        message: costImpact.estimate_add_on_total > 0
          ? 'Flight, stay, and event bookings are folded into the known per-person estimate.'
          : tripPacket.quote_plan?.message || 'Saved local or place costs are tracked in the wallet without double-counting the route estimate.',
      },
      known_per_person: {
        ...(tripPacket.known_per_person || {}),
        low: combinedKnownLow ?? tripPacket.known_per_person?.low,
        high: combinedKnownHigh ?? tripPacket.known_per_person?.high,
        label: combinedLabel,
      },
      quick_stats: [
        savedDetailStat,
        confirmedDetailStat,
        ...(savedCostStat ? [savedCostStat] : []),
        ...existingStats,
      ].slice(0, 7),
      required_actions: [...reservationActions, ...existingActions].slice(0, 5),
      booking_command_center: bookingCommandCenter || tripPacket.booking_command_center,
      booking_checklist: nextChecklist || tripPacket.booking_checklist,
      next_step: nextStep,
    },
  };
};

const placeFromRecommendation = (item: any): Place => {
  const name = item.name || item.display?.name || 'Unknown place';
  const types = item.display?.types || [];
  const scoringProfile = item.scoring_profile
    || item.components?.scoring_profile
    || item.ranking?.scoring_profile;
  const place = {
    place_id: String(item.place_id || item.provider_place_id),
    provider: item.provider,
    provider_place_id: item.provider_place_id,
    request_id: item.request_id,
    rank_position: item.rank_position,
    name,
    vicinity: item.display?.vicinity || `${item.distance_meters ?? 'Unknown'} meters away`,
    types,
    category: item.category,
    scoring_profile: scoringProfile,
    explanation: item.explanation,
    explanation_details: item.explanation_details || [],
    recommendation_story: item.recommendation_story,
    repeat_after_exhaustion: item.repeat_after_exhaustion,
    history: item.history,
    score_components: item.components,
    ranking: item.ranking,
    learned_score: item.learned_score,
    learned_rank_position: item.learned_rank_position,
    authenticity_evidence: item.authenticity_evidence,
    diversity_groups: item.diversity_groups,
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
    member_fit: item.member_fit || [],
  };

  return {
    ...place,
    tag_groups: tagGroupIdsForPlace(place),
  };
};

type HomeScreenProps = {
  user?: User | null;
};

const greetingForNow = () => {
  const hour = new Date().getHours();
  if (hour < 12) {
    return 'Good morning';
  }
  if (hour < 17) {
    return 'Good afternoon';
  }
  return 'Good evening';
};

const recommendationTimeContext = () => {
  const now = new Date();
  const hour = now.getHours();
  let period: 'morning' | 'midday' | 'afternoon' | 'evening' | 'late_night';
  if (hour >= 5 && hour < 11) {
    period = 'morning';
  } else if (hour >= 11 && hour < 14) {
    period = 'midday';
  } else if (hour >= 14 && hour < 17) {
    period = 'afternoon';
  } else if (hour >= 17 && hour < 22) {
    period = 'evening';
  } else {
    period = 'late_night';
  }

  return {
    local_hour: hour,
    local_weekday: now.getDay(),
    period,
  };
};

const tasteStatusLabel = (status?: string) => {
  if (status === 'personalized') {
    return 'Personalized';
  }
  if (status === 'learning') {
    return 'Learning';
  }
  return 'Warming up';
};

const tasteStatusMessage = (insight?: PreferenceInsight | null) => {
  if (!insight) {
    return 'Launch the balloon to see how Adventour is reading your taste.';
  }
  if (insight.learning_status === 'personalized') {
    return 'Your swipes are giving Adventour a strong signal.';
  }
  if (insight.learning_status === 'learning') {
    return 'A few more accepts, passes, and ratings will sharpen this.';
  }
  return 'Adventour is mostly using onboarding and this trip context so far.';
};

const sessionContextTagLabel = (entry?: SessionContextTag) => {
  const rawTag = entry?.tag || '';
  return tagGroupDisplayLabel(rawTag)
    || entry?.label
    || rawTag.replace(/_/g, ' ')
    || 'this mood';
};

const sessionContextSummaryText = (context?: SessionContextSummary | null) => {
  if (!context || context.status !== 'active' || !(context.signal_count || 0)) {
    return '';
  }

  const positives = (context.top_positive_tags || []).map(sessionContextTagLabel).slice(0, 2);
  const negatives = (context.top_negative_tags || []).map(sessionContextTagLabel).slice(0, 2);
  const positiveText = positives.length ? `toward ${positives.join(', ')}` : 'toward your recent likes';
  const negativeText = negatives.length ? ` and away from ${negatives.join(', ')}` : '';
  return `Adventour is nudging this basket ${positiveText}${negativeText} based on your latest swipes.`;
};

const HomeScreen: React.FC<HomeScreenProps> = ({ user }) => {
  const backendBaseURL = Config.BACKEND_BASE_URL;
  const [places, setPlaces] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [userFeedback, setUserFeedback] = useState<{ place_id: string; feedback: string; tags: string[] }[]>([]);
  const [userId, setUserId] = useState<string>('');
  const [city, setCity] = useState<string>('');
  const [currentCoords, setCurrentCoords] = useState<Coordinates | null>(null);
  const [locationMode, setLocationMode] = useState<LocationMode>('none');
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [originSuggestions, setOriginSuggestions] = useState<any[]>([]);
  const [emptyMessage, setEmptyMessage] = useState<string>('');
  const [hasLoadedRecommendations, setHasLoadedRecommendations] = useState(false);
  const [autoRefillAvailable, setAutoRefillAvailable] = useState(false);
  const [radiusOption, setRadiusOption] = useState<RadiusOption>(RADIUS_OPTIONS[1]);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [distanceOpen, setDistanceOpen] = useState(false);
  const [tagDropdownOpen, setTagDropdownOpen] = useState(false);
  const [discoverMode, setDiscoverMode] = useState<DiscoverMode>('spontaneous');
  const [tripSetupOpen, setTripSetupOpen] = useState(false);
  const [routeControlsOpen, setRouteControlsOpen] = useState(false);
  const [calendarPicker, setCalendarPicker] = useState<'start' | 'end' | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [selectedTagGroup, setSelectedTagGroup] = useState<string>('all');
  const [excludedTagGroups, setExcludedTagGroups] = useState<string[]>([]);
  const [friends, setFriends] = useState<FriendOption[]>([]);
  const [selectedFriendIds, setSelectedFriendIds] = useState<number[]>([]);
  const [boostedFriendQueryTags, setBoostedFriendQueryTags] = useState<string[]>([]);
  const [preferenceInsights, setPreferenceInsights] = useState<PreferenceInsight[]>([]);
  const [groupFitSummary, setGroupFitSummary] = useState<GroupFitSummary | null>(null);
  const [slateSummary, setSlateSummary] = useState<SlateSummary | null>(null);
  const [recommendationQuality, setRecommendationQuality] = useState<RecommendationQualitySummary | null>(null);
  const [basketScenarioReadiness, setBasketScenarioReadiness] = useState<ScenarioReadinessSummary | null>(null);
  const [recommendationFilterSummary, setRecommendationFilterSummary] = useState<RecommendationFilterSummary | null>(null);
  const [retrievalContext, setRetrievalContext] = useState<RetrievalContext | null>(null);
  const [sessionContext, setSessionContext] = useState<SessionContextSummary | null>(null);
  const [learnedRerankSummary, setLearnedRerankSummary] = useState<LearnedRerankSummary | null>(null);
  const [learnedRankerStatusLoading, setLearnedRankerStatusLoading] = useState(false);
  const [basketComparisons, setBasketComparisons] = useState<BasketComparison[]>([]);
  const [recommendedBasketProfile, setRecommendedBasketProfile] = useState<string | null>(null);
  const [basketProviderUsage, setBasketProviderUsage] = useState<ProviderUsageSummary | null>(null);
  const [localEventPreview, setLocalEventPreview] = useState<LocalEventsPayload | null>(null);
  const [localEventsLoading, setLocalEventsLoading] = useState(false);
  const [scoringProfile, setScoringProfile] = useState<ScoringProfileOption>(SCORING_PROFILE_OPTIONS[0]);
  const [planOption] = useState<PlanOption>(PLAN_OPTIONS[0]);
  const [paceOption, setPaceOption] = useState<PaceOption>(PACE_OPTIONS[1]);
  const [budgetOption, setBudgetOption] = useState<BudgetOption>(BUDGET_OPTIONS[1]);
  const [tripOrigin, setTripOrigin] = useState('');
  const [tripStartDate, setTripStartDate] = useState('');
  const [tripEndDate, setTripEndDate] = useState('');
  const [lodgingOption, setLodgingOption] = useState<LodgingOption>(LODGING_OPTIONS[0]);
  const [stayNeighborhood, setStayNeighborhood] = useState('');
  const [localTransportOption, setLocalTransportOption] = useState<LocalTransportOption>(LOCAL_TRANSPORT_OPTIONS[0]);
  const [itineraryPlan, setItineraryPlan] = useState<ItineraryPlan | null>(null);
  const [swappedItinerarySlots, setSwappedItinerarySlots] = useState<string[]>([]);
  const [itineraryLoading, setItineraryLoading] = useState(false);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  const [itineraryComparisons, setItineraryComparisons] = useState<ItineraryComparison[]>([]);
  const [recommendedComparisonProfile, setRecommendedComparisonProfile] = useState<string | null>(null);
  const [itineraryProviderUsage, setItineraryProviderUsage] = useState<ProviderUsageSummary | null>(null);
  const [destinationScoutInput, setDestinationScoutInput] = useState('');
  const [destinationScoutLoading, setDestinationScoutLoading] = useState(false);
  const [destinationComparisons, setDestinationComparisons] = useState<DestinationComparison[]>([]);
  const [recommendedDestinationLabel, setRecommendedDestinationLabel] = useState<string | null>(null);
  const [destinationProviderUsage, setDestinationProviderUsage] = useState<ProviderUsageSummary | null>(null);
  const [savedReservations, setSavedReservations] = useState<TravelReservation[]>([]);
  const [pendingItineraryReservationIds, setPendingItineraryReservationIds] = useState<number[]>([]);
  const [reservationDraft, setReservationDraft] = useState<ReservationDraft | null>(null);
  const [reservationSaving, setReservationSaving] = useState(false);
  const [eventDraftOpen, setEventDraftOpen] = useState(false);
  const [eventDraft, setEventDraft] = useState<LocalEventDraft>({
    title: '',
    starts_at: '',
    category: '',
    description: '',
    source_url: '',
    reservation_url: '',
  });
  const [eventSaving, setEventSaving] = useState(false);
  const [selectedPlace, setSelectedPlace] = useState<Place | null>(null);
  const [activeAdventour, setActiveAdventour] = useState<AdventourSession | null>(null);
  const [journeyLoading, setJourneyLoading] = useState(false);
  const autocompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const originAutocompleteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scrollRef = useRef<ScrollView>(null);
  const filterPanelAnim = useRef(new Animated.Value(0)).current;
  const recentlyDecidedPlaceIds = useRef(new Set<string>());
  const autoRefillInFlight = useRef(false);
  const pendingBasketScroll = useRef(false);
  const lastRecommendationScope = useRef<string | null>(null);
  const adoptingDestinationPlan = useRef(false);
  const [basketOffsetY, setBasketOffsetY] = useState(0);
  const [tripDetailsOffsetY, setTripDetailsOffsetY] = useState(0);
  const [eventSectionOffsetY, setEventSectionOffsetY] = useState(0);
  const [bookingSectionOffsetY, setBookingSectionOffsetY] = useState(0);
  const displayName = user?.display_name || user?.username || 'Adventourer';
  const hasLaunchPoint = Boolean(currentCoords);
  const autoScoutSelected = scoringProfile.id === 'auto_scout';
  const itineraryPartySize = Math.max(1, itineraryPlan?.price_breakdown?.party_size || selectedFriendIds.length + 1);
  const pendingItineraryReservationSet = new Set(pendingItineraryReservationIds);
  const itinerarySavedReservations = savedReservations.filter((reservation) => (
    (activeAdventour?.id && reservation.adventour_session_id === activeAdventour.id)
    || (!activeAdventour?.id && pendingItineraryReservationSet.has(reservation.id))
  ));
  const savedReservationCostImpact = reservationCostImpact(itinerarySavedReservations);
  const savedReservationCostTotal = savedReservationCostImpact.tracked_total;
  const savedReservationEstimateAddOnTotal = savedReservationCostImpact.estimate_add_on_total;
  const savedReservationCostPerPerson = savedReservationCostTotal / itineraryPartySize;
  const savedReservationEstimateAddOnPerPerson = savedReservationEstimateAddOnTotal / itineraryPartySize;
  const savedReservationTypeCounts = itinerarySavedReservations.reduce<Record<string, number>>((counts, reservation) => {
    counts[reservation.reservation_type] = (counts[reservation.reservation_type] || 0) + 1;
    return counts;
  }, {});
  const recommendationScope = JSON.stringify({
    locationMode,
    latitude: currentCoords?.latitude ?? null,
    longitude: currentCoords?.longitude ?? null,
    radius: radiusOption.id,
    scout: scoringProfile.id,
    friends: selectedFriendIds,
    excluded: excludedTagGroups,
  });

  useEffect(() => {
    const getOrCreateUserId = async () => {
      try {
        let id = await AsyncStorage.getItem('user_id');
        if (!id) {
          id = uuidv4();
          await AsyncStorage.setItem('user_id', id);
        }
        setUserId(id);
      } catch (e) {
        console.error("Failed to initialize user ID", e);
      }
    };
    getOrCreateUserId();
  }, []);

  useEffect(() => {
    const loadActiveAdventour = async () => {
      try {
        const adventour = await AdventourService.getActive();
        setActiveAdventour(adventour);
      } catch (error) {
        console.error('Error loading active Adventour:', describeAxiosError(error));
      }
    };

    loadActiveAdventour();
  }, []);

  const filteredPlaces = selectedTagGroup === 'all'
    ? places
    : places.filter((place) => place.tag_groups?.includes(selectedTagGroup));

  const tagGroupCounts = TAG_GROUPS.reduce<Record<string, number>>((counts, group) => {
    counts[group.id] = places.filter((place) => place.tag_groups?.includes(group.id)).length;
    return counts;
  }, {});

  const selectedTagLabel = selectedTagGroup === 'all'
    ? 'All picks'
    : tagGroupDisplayLabel(selectedTagGroup) || 'All picks';
  const excludedTagLabels = excludedTagGroups
    .map((groupId) => tagGroupDisplayLabel(groupId))
    .filter(Boolean);
  const activeFriendBoostLabels = Array.from(new Set(
    (retrievalContext?.boost_query_tags?.length
      ? retrievalContext.boost_query_tags
      : boostedFriendQueryTags
    ).map((tag) => tagGroupDisplayLabel(tag) || tag.replace(/_/g, ' '))
  )).slice(0, 3);
  const sessionPulseActive = sessionContext?.status === 'active' && (sessionContext.signal_count || 0) > 0;
  const sessionPulseSummary = sessionContextSummaryText(sessionContext);
  const sessionPulsePositiveTags = (sessionContext?.top_positive_tags || [])
    .map(sessionContextTagLabel)
    .slice(0, 3);
  const sessionPulseNegativeTags = (sessionContext?.top_negative_tags || [])
    .map(sessionContextTagLabel)
    .slice(0, 2);
  const selectedFriends = friends.filter((friend) => selectedFriendIds.includes(friend.id));
  const partyLabel = selectedFriends.length
    ? `You + ${selectedFriends.map((friend) => friend.display_name || friend.username).join(', ')}`
    : 'Just you';
  const partySummaryLabel = selectedFriends.length
    ? `Party: You + ${selectedFriends[0].display_name || selectedFriends[0].username}${selectedFriends.length > 1 ? ` +${selectedFriends.length - 1}` : ''}`
    : 'Solo scout';
  const scoutStyleLabel = scoringProfile.label;
  const learnedRerankStatus = learnedRerankStatusMessage(scoringProfile, learnedRerankSummary);
  const learnedReadyForAutoScout = learnedRankerReadyForAutoScout(learnedRerankSummary);
  const autoScoutComparisonOptions = useMemo(() => AUTO_SCOUT_COMPARISON_OPTIONS.filter((option) => (
    !option.learnedRerank || learnedReadyForAutoScout
  )), [learnedReadyForAutoScout]);
  const autoScoutSkippedLearned = !learnedReadyForAutoScout && Boolean(LEARNED_SCORING_PROFILE);
  const autoScoutLearnedSkipMessage = autoScoutSelected && autoScoutSkippedLearned
    ? learnedRankerAutoScoutSkipMessage(learnedRerankSummary, learnedRankerStatusLoading)
    : null;
  const basketProviderUsageLabel = providerUsageLabel(basketProviderUsage);
  const itineraryProviderUsageLabel = providerUsageLabel(itineraryProviderUsage);
  const destinationProviderUsageLabel = providerUsageLabel(destinationProviderUsage);
  const displayedLearnedRerankStatus = scoringProfile.learnedRerank && learnedRankerStatusLoading
    ? 'Checking learned beta status...'
    : learnedRerankStatus;
  const learnedTrainingHealthChips = learnedTrainingDataHealthChips(learnedRerankSummary?.training_data_health);
  const ownPreferenceInsight = preferenceInsights.find((insight) => insight.user_id === user?.id) || preferenceInsights[0] || null;
  const visiblePreferenceInsights = preferenceInsights.length ? preferenceInsights : [];
  const topTasteTags = ownPreferenceInsight?.top_categories?.length
    ? ownPreferenceInsight.top_categories.slice(0, 3)
    : [];
  const avoidedTasteTags = ownPreferenceInsight?.avoided_categories?.length
    ? ownPreferenceInsight.avoided_categories.slice(0, 2)
    : [];
  const confidencePercent = ownPreferenceInsight ? Math.round((ownPreferenceInsight.confidence || 0) * 100) : 0;
  const groupFitPercent = groupFitSummary ? Math.round((groupFitSummary.average_fit || 0) * 100) : 0;
  const groupFairnessPercent = groupFitSummary?.fairness_score !== undefined && groupFitSummary?.fairness_score !== null
    ? Math.round(groupFitSummary.fairness_score * 100)
    : null;

  useEffect(() => {
    const loadFriends = async () => {
      try {
        const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/friends`);
        setFriends(response.data.friends || []);
      } catch (error) {
        console.error('Error loading Discover friends:', describeAxiosError(error));
      }
    };

    loadFriends();
  }, []);

  const refreshLearnedRankerStatus = useCallback(async () => {
    setLearnedRankerStatusLoading(true);
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/recommendations/learned-ranker/status`);
      setLearnedRerankSummary(response.data.learned_rerank || null);
    } catch (error) {
      console.error('Error loading learned ranker status:', describeAxiosError(error));
    } finally {
      setLearnedRankerStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshLearnedRankerStatus();
  }, [refreshLearnedRankerStatus]);

  useEffect(() => {
    if (scoringProfile.learnedRerank && !learnedRerankSummary && !learnedRankerStatusLoading) {
      refreshLearnedRankerStatus();
    }
  }, [
    learnedRankerStatusLoading,
    learnedRerankSummary,
    refreshLearnedRankerStatus,
    scoringProfile.learnedRerank,
  ]);

  const refreshPreferenceInsights = useCallback(async () => {
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/recommendations/preferences`, {
        params: selectedFriendIds.length ? { member_ids: selectedFriendIds.join(',') } : undefined,
      });
      const insight = response.data.preference_insights;
      setPreferenceInsights(Array.isArray(insight) ? insight : insight ? [insight] : []);
    } catch (error) {
      console.error('Error loading preference insights:', describeAxiosError(error));
    }
  }, [selectedFriendIds]);

  useEffect(() => {
    refreshPreferenceInsights();
  }, [refreshPreferenceInsights]);

  const loadReservations = useCallback(async () => {
    try {
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/reservations`);
      setSavedReservations(response.data.reservations || []);
    } catch (error) {
      console.error('Error loading reservations:', describeAxiosError(error));
    }
  }, []);

  useEffect(() => {
    loadReservations();
  }, [loadReservations]);

  useEffect(() => {
    if (!itineraryPlan && swappedItinerarySlots.length) {
      setSwappedItinerarySlots([]);
    }
  }, [itineraryPlan, swappedItinerarySlots.length]);

  useEffect(() => {
    if (selectedTagGroup !== 'all' && places.length > 0 && filteredPlaces.length === 0) {
      setSelectedTagGroup('all');
    }
  }, [filteredPlaces.length, places.length, selectedTagGroup]);

  useEffect(() => {
    if (lastRecommendationScope.current === null) {
      lastRecommendationScope.current = recommendationScope;
      return;
    }

    if (lastRecommendationScope.current === recommendationScope) {
      return;
    }

    lastRecommendationScope.current = recommendationScope;
    const preserveAdoptedDestinationPlan = adoptingDestinationPlan.current;
    if (!preserveAdoptedDestinationPlan) {
      setItineraryPlan(null);
      setSwappedItinerarySlots([]);
      setItineraryComparisons([]);
      setRecommendedComparisonProfile(null);
      setItineraryProviderUsage(null);
      setDestinationComparisons([]);
      setRecommendedDestinationLabel(null);
      setDestinationProviderUsage(null);
    }
    setBasketComparisons([]);
    setRecommendedBasketProfile(null);
    setBasketProviderUsage(null);
    setLocalEventPreview(null);
    setSlateSummary(null);
    setRecommendationQuality(null);
    setBasketScenarioReadiness(null);
    setRecommendationFilterSummary(null);
    setRetrievalContext(null);
    setSessionContext(null);

    if (!places.length && !hasLoadedRecommendations) {
      return;
    }

    setPlaces([]);
    setHasLoadedRecommendations(false);
    setAutoRefillAvailable(false);
    setSelectedTagGroup('all');
    setTagDropdownOpen(false);
    recentlyDecidedPlaceIds.current.clear();
    setEmptyMessage('Launch the balloon again so this basket matches your latest party, scout style, and skips.');
  }, [hasLoadedRecommendations, places.length, recommendationScope]);

  useEffect(() => {
    if (adoptingDestinationPlan.current) {
      adoptingDestinationPlan.current = false;
      return;
    }

    setItineraryComparisons([]);
    setRecommendedComparisonProfile(null);
    setItineraryProviderUsage(null);
    setDestinationComparisons([]);
    setRecommendedDestinationLabel(null);
    setDestinationProviderUsage(null);
    setBasketComparisons([]);
    setRecommendedBasketProfile(null);
    setBasketProviderUsage(null);
    setLocalEventPreview(null);
    setRecommendationQuality(null);
    setBasketScenarioReadiness(null);
    setRecommendationFilterSummary(null);
    setRetrievalContext(null);
    setSessionContext(null);
  }, [
    city,
    currentCoords,
    radiusOption.id,
    selectedFriendIds,
    excludedTagGroups,
    planOption.id,
    paceOption.id,
    budgetOption.id,
    tripOrigin,
    tripStartDate,
    tripEndDate,
    lodgingOption.id,
    stayNeighborhood,
    localTransportOption.id,
  ]);

  useEffect(() => {
    Animated.timing(filterPanelAnim, {
      toValue: filtersOpen ? 1 : 0,
      duration: 170,
      useNativeDriver: true,
    }).start();
  }, [filterPanelAnim, filtersOpen]);

  const filterPanelStyle = {
    opacity: filterPanelAnim,
    transform: [
      {
        translateY: filterPanelAnim.interpolate({
          inputRange: [0, 1],
          outputRange: [-6, 0],
        }),
      },
    ],
  };

  const switchDiscoverMode = (mode: DiscoverMode) => {
    setDiscoverMode(mode);
    setFiltersOpen(false);
    setRouteControlsOpen(false);
    setCalendarPicker(null);
    setOriginSuggestions([]);
    setTripSetupOpen(mode === 'itinerary');
  };

  const toggleTravelFriend = (friendId: number) => {
    setSelectedFriendIds((current) => (
      current.includes(friendId)
        ? current.filter((id) => id !== friendId)
        : [...current, friendId]
    ));
  };

  const toggleExcludedTagGroup = (groupId: string) => {
    setExcludedTagGroups((current) => (
      current.includes(groupId)
        ? current.filter((id) => id !== groupId)
        : [...current, groupId]
    ));
    setItineraryPlan(null);
  };

  const applyDateShortcut = (shortcutId: (typeof DATE_SHORTCUTS)[number]['id']) => {
    const range = shortcutTripRange(shortcutId);
    setTripStartDate(range.start);
    setTripEndDate(range.end);
    setItineraryPlan(null);
  };

  const tripDatesPayload = {
    ...(tripStartDate.trim() ? { start: tripStartDate.trim() } : {}),
    ...(tripEndDate.trim() ? { end: tripEndDate.trim() } : {}),
  };
  const tripDateError = tripDateValidationMessage(tripStartDate, tripEndDate);
  const hasTripDateRange = Boolean(tripStartDate.trim() && tripEndDate.trim() && !tripDateError);
  const itineraryDayCount = hasTripDateRange
    ? tripDayCountFromDates(planOption.days, tripStartDate, tripEndDate)
    : planOption.days;
  const inferredPlanOption = planOptionForDayCount(itineraryDayCount);
  const fullItineraryReady = hasLaunchPoint && hasTripDateRange && !itineraryLoading;
  const tripDateSummary = tripStartDate && tripEndDate
    ? `${tripStartDate} to ${tripEndDate}`
    : 'Pick dates';
  const tripSetupSummary = [
    tripDateSummary,
    budgetOption.label,
    paceOption.label,
    tripOrigin.trim() ? `from ${tripOrigin.trim()}` : null,
    stayNeighborhood.trim() ? `stay near ${stayNeighborhood.trim()}` : null,
  ].filter(Boolean).join(' - ');

  const itineraryRequestPayload = ({
    profile = scoringProfile,
    useLearnedRerank = scoringProfile.learnedRerank,
    radius = radiusOption,
    excludedGroups = excludedTagGroups,
    boostTags = boostedFriendQueryTags,
  }: {
    profile?: ScoringProfileOption | string;
    useLearnedRerank?: boolean;
    radius?: RadiusOption;
    excludedGroups?: string[];
    boostTags?: string[];
  } = {}) => ({
    location: currentCoords,
    radius_meters: radius.meters,
    member_ids: selectedFriendIds,
    party_size: selectedFriendIds.length + 1,
    days: itineraryDayCount,
    destination_label: city || 'your launch point',
    constraints: {
      avoid_chains: true,
      scoring_profile: backendScoringProfileId(profile),
      ...(useLearnedRerank ? { learned_rerank: true } : {}),
      excluded_tag_groups: excludedGroups,
      trip_style: inferredPlanOption.id,
      pace: paceOption.id,
      budget_profile: budgetOption.id,
      ...(tripOrigin.trim() ? { origin_label: tripOrigin.trim() } : {}),
      ...(Object.keys(tripDatesPayload).length ? { travel_dates: tripDatesPayload } : {}),
      lodging_type: lodgingOption.id,
      ...(stayNeighborhood.trim() ? { stay_neighborhood: stayNeighborhood.trim() } : {}),
      ...(localTransportOption.id !== 'auto' ? { preferred_local_transport: localTransportOption.id } : {}),
      ...(boostTags.length ? { boost_query_tags: boostTags } : {}),
    },
  });
  const itineraryComparisonPayload = () => ({
    ...itineraryRequestPayload({ profile: scoringProfile, useLearnedRerank: false }),
    scoring_profiles: autoScoutComparisonOptions.map((option) => option.id),
    include_plans: true,
  });

  const destinationLabels = () => destinationScoutInput
    .split(/[\n;]/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 6);

  const destinationComparisonConstraints = () => ({
    avoid_chains: true,
    excluded_tag_groups: excludedTagGroups,
    trip_style: inferredPlanOption.id,
    pace: paceOption.id,
    budget_profile: budgetOption.id,
    ...(tripOrigin.trim() ? { origin_label: tripOrigin.trim() } : {}),
    ...(Object.keys(tripDatesPayload).length ? { travel_dates: tripDatesPayload } : {}),
    lodging_type: lodgingOption.id,
    ...(stayNeighborhood.trim() ? { stay_neighborhood: stayNeighborhood.trim() } : {}),
    ...(localTransportOption.id !== 'auto' ? { preferred_local_transport: localTransportOption.id } : {}),
    ...(boostedFriendQueryTags.length ? { boost_query_tags: boostedFriendQueryTags } : {}),
  });

  const geocodeDestinationCandidate = async (label: string, id: string): Promise<DestinationCandidate> => {
    const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
      params: { address: label },
    });
    const resolvedLocation = {
      latitude: Number(response.data.latitude),
      longitude: Number(response.data.longitude),
    };
    if (!Number.isFinite(resolvedLocation.latitude) || !Number.isFinite(resolvedLocation.longitude)) {
      throw new Error(`Unable to resolve coordinates for ${label}`);
    }
    return {
      id,
      label,
      location: resolvedLocation,
      radius_meters: radiusOption.meters,
      source: 'manual_compare',
    };
  };

  const loadItineraryPlan = async ({
    scoringProfileOverride,
    radiusOptionOverride,
    excludedTagGroupsOverride,
    boostQueryTagsOverride,
  }: {
    scoringProfileOverride?: ScoringProfileOption;
    radiusOptionOverride?: RadiusOption;
    excludedTagGroupsOverride?: string[];
    boostQueryTagsOverride?: string[];
  } = {}) => {
    if (!currentCoords) {
      Alert.alert('Pick a launch point', 'Choose a city, neighborhood, or place before Adventour builds a plan.');
      return;
    }
    if (tripDateError) {
      Alert.alert('Check trip dates', tripDateError);
      return;
    }

    setItineraryLoading(true);
    setItineraryPlan(null);
    setSwappedItinerarySlots([]);
    setPendingItineraryReservationIds([]);
    try {
      const activeScoringProfile = scoringProfileOverride || scoringProfile;
      const activeRadiusOption = radiusOptionOverride || radiusOption;
      const activeExcludedTagGroups = excludedTagGroupsOverride ?? excludedTagGroups;
      const activeBoostQueryTags = boostQueryTagsOverride ?? boostedFriendQueryTags;
      const activeAutoScoutSelected = activeScoringProfile.id === 'auto_scout';
      const activeItineraryPayload = itineraryRequestPayload({
        profile: activeScoringProfile,
        useLearnedRerank: activeScoringProfile.learnedRerank,
        radius: activeRadiusOption,
        excludedGroups: activeExcludedTagGroups,
        boostTags: activeBoostQueryTags,
      });

      if (activeAutoScoutSelected) {
        const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations/itinerary/compare`, {
          ...activeItineraryPayload,
          scoring_profiles: autoScoutComparisonOptions.map((option) => option.id),
          include_plans: true,
        });
        const comparisons: ItineraryComparison[] = response.data.comparisons || [];
        const recommendedProfile = response.data.recommended_profile || comparisons[0]?.scoring_profile || null;
        const recommendedComparison = comparisons.find((comparison) => comparison.scoring_profile === recommendedProfile) || comparisons[0];

        setItineraryComparisons(comparisons);
        setRecommendedComparisonProfile(recommendedProfile);
        setItineraryProviderUsage(response.data.provider_usage || null);
        if (recommendedComparison?.plan) {
          setItineraryPlan(withSwapSummary(recommendedComparison.plan));
          setLearnedRerankSummary(recommendedComparison.plan.learned_rerank || null);
          return;
        }

        throw new Error('Auto scout did not return a route plan.');
      }

      setItineraryComparisons([]);
      setRecommendedComparisonProfile(null);
      setItineraryProviderUsage(null);
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations/itinerary`, activeItineraryPayload);
      setItineraryPlan(response.data);
      setLearnedRerankSummary(response.data.learned_rerank || null);
    } catch (error) {
      console.error('Error building itinerary plan:', describeAxiosError(error));
      Alert.alert('Plan not ready', 'Adventour could not build a route for this launch point yet.');
    } finally {
      setItineraryLoading(false);
    }
  };

  const compareItineraryProfiles = async () => {
    if (!currentCoords) {
      Alert.alert('Pick a launch point', 'Choose a city, neighborhood, or place before comparing scout styles.');
      return;
    }
    if (tripDateError) {
      Alert.alert('Check trip dates', tripDateError);
      return;
    }

    setComparisonLoading(true);
    try {
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations/itinerary/compare`, itineraryComparisonPayload());
      setItineraryComparisons(response.data.comparisons || []);
      setRecommendedComparisonProfile(response.data.recommended_profile || null);
      setItineraryProviderUsage(response.data.provider_usage || null);
    } catch (error) {
      console.error('Error comparing itinerary profiles:', describeAxiosError(error));
      Alert.alert('Compare not ready', 'Adventour could not compare scout styles for this launch point yet.');
    } finally {
      setComparisonLoading(false);
    }
  };

  const compareDestinations = async () => {
    if (tripDateError) {
      Alert.alert('Check trip dates', tripDateError);
      return;
    }

    const seenLabels = new Set<string>();
    const candidates: DestinationCandidate[] = [];
    const currentLabel = city.trim();
    if (currentCoords && currentLabel) {
      seenLabels.add(currentLabel.toLowerCase());
      candidates.push({
        id: 'current_launch_point',
        label: currentLabel,
        location: currentCoords,
        radius_meters: radiusOption.meters,
        source: 'current_launch_point',
      });
    }

    const typedLabels = destinationLabels().filter((label) => {
      const key = label.toLowerCase();
      if (seenLabels.has(key)) {
        return false;
      }
      seenLabels.add(key);
      return true;
    });

    if (candidates.length + typedLabels.length < 2) {
      Alert.alert(
        'Add destinations',
        'Add at least two cities or places to compare, or set a launch point and add one more destination.'
      );
      return;
    }

    setDestinationScoutLoading(true);
    setDestinationComparisons([]);
    setRecommendedDestinationLabel(null);
    setDestinationProviderUsage(null);
    try {
      const resolvedCandidates = await Promise.all(
        typedLabels.map((label, index) => geocodeDestinationCandidate(label, `candidate_${index + 1}`))
      );
      const destinations = [...candidates, ...resolvedCandidates];
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/recommendations/destinations/compare`, {
        destinations,
        days: itineraryDayCount,
        party_size: selectedFriendIds.length + 1,
        member_ids: selectedFriendIds,
        scoring_profiles: autoScoutComparisonOptions.map((option) => option.id),
        constraints: destinationComparisonConstraints(),
        include_plans: true,
        include_profile_comparisons: true,
      });
      setDestinationComparisons(response.data.comparisons || []);
      setRecommendedDestinationLabel(response.data.recommended_destination_label || null);
      setDestinationProviderUsage(response.data.provider_usage || null);
    } catch (error) {
      console.error('Error comparing destinations:', describeAxiosError(error));
      Alert.alert('Trip scout not ready', 'Adventour could not compare those destinations yet. Try more specific city names.');
    } finally {
      setDestinationScoutLoading(false);
    }
  };

  const useDestinationComparison = (comparison: DestinationComparison) => {
    const destination = comparison.destination;
    const willChangeLaunchPoint = Boolean(destination?.label || destination?.location);
    if (willChangeLaunchPoint) {
      adoptingDestinationPlan.current = true;
    }
    if (destination?.label) {
      setCity(destination.label);
    }
    if (destination?.location) {
      setCurrentCoords(destination.location);
      setLocationMode('manual');
    }
    const nextStyle = scoutStyleForId(comparison.scoring_profile);
    if (nextStyle) {
      setScoringProfile(nextStyle);
    }
    if (comparison.profile_comparisons?.length) {
      setItineraryComparisons(comparison.profile_comparisons);
      setRecommendedComparisonProfile(comparison.scoring_profile);
    }
    if (comparison.plan) {
      setItineraryPlan(withSwapSummary(comparison.plan));
      setSwappedItinerarySlots([]);
      setPendingItineraryReservationIds([]);
    }
    setPlaces([]);
    setHasLoadedRecommendations(false);
    setAutoRefillAvailable(false);
    setSelectedTagGroup('all');
    setTagDropdownOpen(false);
    setBasketComparisons([]);
    setRecommendedBasketProfile(null);
    setBasketProviderUsage(null);
    setLocalEventPreview(null);
    setSlateSummary(null);
    setRecommendationQuality(null);
    setBasketScenarioReadiness(null);
    setRecommendationFilterSummary(null);
    setRetrievalContext(null);
    setSessionContext(null);
    recentlyDecidedPlaceIds.current.clear();
    setEmptyMessage('Launch the balloon when you want spontaneous picks for this trip.');
    setTimeout(() => {
      adoptingDestinationPlan.current = false;
      scrollRef.current?.scrollTo({ y: tripDetailsOffsetY ? Math.max(0, tripDetailsOffsetY - 12) : 0, animated: true });
    }, 120);
  };

  const useItineraryComparison = (comparison: ItineraryComparison) => {
    const nextStyle = scoutStyleForId(comparison.scoring_profile);
    if (nextStyle) {
      setScoringProfile(nextStyle);
    }
    if (comparison.plan) {
      setItineraryPlan(withSwapSummary(comparison.plan));
      setSwappedItinerarySlots([]);
      setPendingItineraryReservationIds([]);
    } else {
      setItineraryPlan(null);
    }
  };

  const swapItineraryStop = (dayIndex: number, stopIndex: number, alternativeIndex: number) => {
    const stopSnapshot = itineraryPlan?.days[dayIndex]?.stops[stopIndex];
    const swapKey = itineraryStopSwapKey(dayIndex, stopIndex, stopSnapshot);
    if (!stopSnapshot?.alternatives[alternativeIndex]) {
      return;
    }

    setItineraryPlan((current) => {
      if (!current) {
        return current;
      }

      const nextPlan: ItineraryPlan = {
        ...current,
        days: current.days.map((day) => ({
          ...day,
          stops: day.stops.map((stop) => ({
            ...stop,
            alternatives: [...stop.alternatives],
          })),
        })),
      };
      const stop = nextPlan.days[dayIndex]?.stops[stopIndex];
      const alternative = stop?.alternatives[alternativeIndex];
      if (!stop || !alternative) {
        return current;
      }

      const previousRecommendation = {
        ...stop.recommendation,
        diversity_groups: stop.recommendation.diversity_groups || stop.diversity_groups || diversityGroupsForItineraryRecommendation(stop.recommendation),
      };
      stop.recommendation = alternative;
      stop.diversity_groups = diversityGroupsForItineraryRecommendation(alternative);
      stop.party_fit_summary = partyFitSummaryForItineraryRecommendation(alternative);
      stop.why_this_stop = whyThisStopForItineraryRecommendation(stop, alternative);
      stop.swap_history = {
        swapped: true,
        swapped_at: new Date().toISOString(),
        from_place_id: previousRecommendation.place_id,
        from_name: itineraryPlaceName(previousRecommendation),
        to_place_id: alternative.place_id,
        to_name: itineraryPlaceName(alternative),
        impact: alternative.swap_impact,
      };
      stop.alternatives = [
        previousRecommendation,
        ...stop.alternatives.filter((_, index) => index !== alternativeIndex),
      ].slice(0, 3);
      const day = nextPlan.days[dayIndex];
      day.route_balance = routeBalanceForItineraryStops(day.stops);
      day.party_fit = partyFitForItineraryStops(day.stops);
      nextPlan.price_breakdown = priceEstimateForItineraryPlan(nextPlan);
      nextPlan.local_events = localEventsForItineraryPlan(nextPlan);
      nextPlan.route_authenticity = routeAuthenticityForItineraryPlan(nextPlan);
      nextPlan.route_readiness = routeReadinessForItineraryPlan(nextPlan);
      nextPlan.route_explanation = routeExplanationForItineraryPlan(nextPlan);
      nextPlan.launch_checklist = launchChecklistForItineraryPlan(nextPlan);
      nextPlan.scenario_readiness = scenarioReadinessForItineraryPlan(nextPlan);
      nextPlan.itinerary_story = itineraryStoryForItineraryPlan(nextPlan);
      nextPlan.swap_guide = swapGuideForItineraryPlan(nextPlan);
      nextPlan.route_model_confidence = routeModelConfidenceForItineraryPlan(nextPlan);
      nextPlan.trip_packet = tripPacketForItineraryPlan(nextPlan);
      return withSwapSummary(nextPlan);
    });
    setSwappedItinerarySlots((current) => (
      current.includes(swapKey) ? current : [...current, swapKey]
    ));
  };

  const applySwapGuideSuggestion = (suggestion?: NonNullable<SwapGuide['best_swaps']>[number]) => {
    if (!suggestion || !itineraryPlan) {
      return;
    }

    const normalizeId = (value?: number | string | null) => (
      value === undefined || value === null ? null : String(value)
    );
    const targetDay = typeof suggestion.day === 'number' ? suggestion.day : null;
    const targetPlaceId = normalizeId(suggestion.to_place_id);
    const targetName = (suggestion.to_name || '').trim().toLowerCase();

    for (let dayIndex = 0; dayIndex < itineraryPlan.days.length; dayIndex += 1) {
      const day = itineraryPlan.days[dayIndex];
      if (targetDay !== null && day.day !== targetDay && dayIndex + 1 !== targetDay) {
        continue;
      }

      for (let stopIndex = 0; stopIndex < day.stops.length; stopIndex += 1) {
        const stop = day.stops[stopIndex];
        if (suggestion.slot_id && stop.slot_id !== suggestion.slot_id) {
          continue;
        }

        const alternativeIndex = (stop.alternatives || []).findIndex((alternative) => {
          const alternativeId = normalizeId(alternative.place_id);
          const alternativeName = itineraryPlaceName(alternative).trim().toLowerCase();
          return (
            (targetPlaceId !== null && alternativeId === targetPlaceId)
            || (targetName.length > 0 && alternativeName === targetName)
          );
        });

        if (alternativeIndex >= 0) {
          swapItineraryStop(dayIndex, stopIndex, alternativeIndex);
          return;
        }
      }
    }

    Alert.alert(
      'Swap moved',
      'Adventour could not find that exact swap anymore. Try one of the swap ideas under the matching stop.',
    );
  };

  const startItineraryAsAdventour = async (skipBookingWarning = false) => {
    if (!itineraryPlan) {
      return;
    }
    if (itineraryPlan.launch_checklist?.can_start === false) {
      Alert.alert(
        'Route needs a little more',
        itineraryPlan.launch_checklist.headline || 'Rebuild or widen the route before starting this planned Adventour.',
      );
      return;
    }
    const bookingComponents = itineraryPlan.booking_plan?.components || [];
    const bookingCoverage = bookingCoverageForPlan(bookingComponents, itinerarySavedReservations);
    const missingBookingItems = bookingCoverage.items.filter((item) => item.status === 'missing');
    if (!skipBookingWarning && missingBookingItems.length) {
      const firstMissing = missingBookingItems[0];
      Alert.alert(
        'Booking details missing',
        `You can start now, but ${missingBookingItems.map((item) => item.label).slice(0, 3).join(', ')} will be missing from the Adventour recap.`,
        [
          {
            text: `Add ${firstMissing.label}`,
            onPress: () => openReservationDraft(firstMissing.component),
          },
          {
            text: 'Start anyway',
            onPress: () => startItineraryAsAdventour(true),
            style: 'destructive',
          },
          { text: 'Cancel', style: 'cancel' },
        ],
      );
      return;
    }

    setJourneyLoading(true);
    try {
      const finalItineraryPlan = withReservationCoverage(
        finalizedItineraryPlan(itineraryPlan),
        itinerarySavedReservations,
      );
      const stops = finalItineraryPlan.days.flatMap((day) => day.stops);
      const reservationIds = pendingItineraryReservationIds.filter((reservationId) =>
        savedReservations.some((reservation) => reservation.id === reservationId && !reservation.adventour_session_id)
      );
      const adventour = await AdventourService.startFromItinerary({
        title: finalItineraryPlan.title,
        destination: finalItineraryPlan.destination || city,
        companion_user_ids: selectedFriendIds,
        price_breakdown: finalItineraryPlan.price_breakdown,
        booking_plan: finalItineraryPlan.booking_plan,
        scoring_profile: finalItineraryPlan.scoring_profile,
        trip_style: finalItineraryPlan.trip_style || inferredPlanOption.id,
        pace: finalItineraryPlan.pace || paceOption.id,
        budget_profile: finalItineraryPlan.budget_profile || budgetOption.id,
        query_tags: finalItineraryPlan.query_tags || [],
        route_readiness: finalItineraryPlan.route_readiness,
        route_explanation: finalItineraryPlan.route_explanation,
        launch_checklist: finalItineraryPlan.launch_checklist || launchChecklistForItineraryPlan(finalItineraryPlan),
        local_events: finalItineraryPlan.local_events,
        trip_packet: finalItineraryPlan.trip_packet,
        scenario_readiness: finalItineraryPlan.scenario_readiness,
        filter_summary: finalItineraryPlan.filter_summary,
        learned_rerank: finalItineraryPlan.learned_rerank,
        swap_summary: finalItineraryPlan.swap_summary,
        destination_scout: finalItineraryPlan.comparison_destination ? {
          source: 'destination_compare',
          selected_destination: finalItineraryPlan.comparison_destination,
          scoring_profile: finalItineraryPlan.comparison_profile || finalItineraryPlan.scoring_profile,
          rank: finalItineraryPlan.comparison_destination_rank,
          explanation: finalItineraryPlan.comparison_destination_explanation,
        } : undefined,
        reservation_ids: reservationIds,
        stops,
      });
      setActiveAdventour(adventour);
      const attachedReservationIds = new Set((adventour.reservations || []).map((reservation) => reservation.id));
      if (attachedReservationIds.size) {
        setSavedReservations((current) => current.map((reservation) => (
          attachedReservationIds.has(reservation.id)
            ? { ...reservation, adventour_session_id: adventour.id }
            : reservation
        )));
      }
      setPendingItineraryReservationIds([]);
      Alert.alert('Adventour ready', 'Your planned route is active. Start with the first stop when you are ready.');
    } catch (error: any) {
      console.error('Error starting planned Adventour:', describeAxiosError(error));
      Alert.alert(
        'Could not start plan',
        axios.isAxiosError(error) && error.response?.data?.error
          ? error.response.data.error
          : 'End any active Adventour and try again.',
      );
    } finally {
      setJourneyLoading(false);
    }
  };

  useEffect(() => {
    if (!pendingBasketScroll.current || loading || !hasLoadedRecommendations || places.length === 0) {
      return;
    }

    pendingBasketScroll.current = false;
    const timeout = setTimeout(() => {
      scrollRef.current?.scrollTo({
        y: Math.max(0, basketOffsetY - 12),
        animated: true,
      });
    }, 180);

    return () => clearTimeout(timeout);
  }, [basketOffsetY, hasLoadedRecommendations, loading, places.length]);

  const showTagDescription = (groupId: string) => {
    if (groupId === 'all') {
      Alert.alert('All picks', 'Show every recommendation from the current search, ordered by Adventour score.');
      return;
    }
    const group = TAG_GROUPS.find((item) => item.id === groupId);
    if (group) {
      Alert.alert(group.label, group.description);
    }
  };

  const openDirectionsForStop = async (stop: AdventourStop) => {
    const destination = stop.display?.latitude && stop.display?.longitude
      ? `${stop.display.latitude},${stop.display.longitude}`
      : stop.display?.name || '';
    const encodedDestination = encodeURIComponent(destination);
    const providerPlaceId = stop.provider_place_id
      ? `&destination_place_id=${encodeURIComponent(stop.provider_place_id)}`
      : '';
    const url = `https://www.google.com/maps/dir/?api=1&destination=${encodedDestination}${providerPlaceId}`;

    try {
      await Linking.openURL(url);
    } catch (error) {
      console.error('Error opening directions:', error);
      Alert.alert('Directions unavailable', 'Adventour could not open your maps app.');
    }
  };

  const handleStartAdventour = async () => {
    setJourneyLoading(true);
    try {
      const adventour = await AdventourService.start(city ? `${city} Adventour` : undefined);
      setActiveAdventour(adventour);
    } catch (error) {
      console.error('Error starting Adventour:', describeAxiosError(error));
      Alert.alert('Could not start Adventour', 'Try again in a moment.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleArriveAtStop = async (stop: AdventourStop) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.arrive(activeAdventour.id, stop.id);
      setActiveAdventour(result.adventour);
    } catch (error) {
      console.error('Error marking arrival:', describeAxiosError(error));
      Alert.alert('Arrival not saved', 'Adventour could not mark this stop as arrived.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleRateStop = async (stop: AdventourStop, rating: number) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.completeStop(activeAdventour.id, stop.id, rating);
      setActiveAdventour(result.adventour);
    } catch (error) {
      console.error('Error completing stop:', describeAxiosError(error));
      Alert.alert('Rating not saved', 'Adventour could not finish this stop.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleSwapActiveStop = async (stop: AdventourStop, alternativeIndex: number) => {
    if (!activeAdventour) {
      return;
    }

    setJourneyLoading(true);
    try {
      const result = await AdventourService.swapStop(activeAdventour.id, stop.id, alternativeIndex);
      setActiveAdventour(result.adventour);
    } catch (error) {
      console.error('Error swapping Adventour stop:', describeAxiosError(error));
      Alert.alert('Swap not saved', 'Adventour could not swap this stop. Try another option or rebuild the route.');
    } finally {
      setJourneyLoading(false);
    }
  };

  const handleEndAdventour = async () => {
    if (!activeAdventour) {
      return;
    }

    Alert.alert(
      'End Adventour?',
      'This will save your journey recap and clear the active trip.',
      [
        { text: 'Keep going', style: 'cancel' },
        {
          text: 'End',
          style: 'destructive',
          onPress: async () => {
            setJourneyLoading(true);
            try {
              const completed = await AdventourService.complete(activeAdventour.id);
              setActiveAdventour(null);
              setEmptyMessage(
                `Adventour complete. Saved ${completed.summary?.stop_count || 0} stop${(completed.summary?.stop_count || 0) === 1 ? '' : 's'} to your Passport.`
              );
            } catch (error) {
              console.error('Error ending Adventour:', describeAxiosError(error));
              Alert.alert('Could not end Adventour', 'Try again in a moment.');
            } finally {
              setJourneyLoading(false);
            }
          },
        },
      ],
    );
  };

  const handleFeedback = async (place: Place, feedback: 'accept' | 'reject') => {
    if (feedback === 'accept' && activeAdventour?.active_stop) {
      Alert.alert(
        'Finish your current stop first',
        'Mark yourself as arrived and rate the current place before adding another Adventour stop.'
      );
      return;
    }

    setUserFeedback((prev) => [
      ...prev,
      { place_id: place.place_id, feedback, tags: place.types },
    ]);
    recentlyDecidedPlaceIds.current.add(place.place_id);
    if (place.provider_place_id) {
      recentlyDecidedPlaceIds.current.add(String(place.provider_place_id));
    }
    setPlaces((prev) => prev.filter((item) => item.place_id !== place.place_id));

    let eventSaved = false;

    try {
      await axios.post(`${backendBaseURL}/api/events`, {
        place_id: place.place_id,
        provider: place.provider,
        provider_place_id: place.provider_place_id,
        event_type: feedback,
        context: selectedTagGroup === 'all' ? 'solo' : selectedTagGroup,
        metadata: {
          source: 'recommendation_deck',
          category: place.category,
          active_tag_group: selectedTagGroup,
          score: place.relevance,
          request_id: place.request_id,
          rank_position: place.rank_position,
          ranking: place.ranking,
          score_components: place.score_components,
          authenticity_evidence: place.authenticity_evidence,
          diversity_groups: place.diversity_groups || [],
          tags: place.types,
          display: {
            name: place.name,
            vicinity: place.vicinity,
            types: place.types,
            category: place.category,
            tag_groups: place.tag_groups || [],
            photo_url: place.photo_url
              ? place.photo_url.replace(Config.BACKEND_BASE_URL, '')
              : undefined,
            photo_attributions: place.photo_attributions || [],
            rating: place.rating,
            user_ratings_total: place.user_ratings_total,
            price_level: place.price_level,
          },
        },
      });
      eventSaved = true;
      refreshPreferenceInsights();
    } catch (error) {
      console.error('Error saving feedback event:', describeAxiosError(error));
      Alert.alert('Feedback not saved', 'The card was removed locally, but Adventour could not save that swipe.');
    }

    if (eventSaved && feedback === 'accept' && activeAdventour) {
      try {
        const result = await AdventourService.addStop(activeAdventour.id, place);
        setActiveAdventour(result.adventour);
      } catch (error: any) {
        const details = describeAxiosError(error);
        console.error('Error adding Adventour stop:', details);

        if (axios.isAxiosError(error) && error.response?.status === 409) {
          try {
            const refreshed = await AdventourService.getActive();
            setActiveAdventour(refreshed);
          } catch (refreshError) {
            console.error('Error refreshing active Adventour:', describeAxiosError(refreshError));
          }

          Alert.alert(
            'Current stop still active',
            error.response.data?.error || 'Finish or rate your current stop before adding another Adventour place.',
          );
          return;
        }

        Alert.alert(
          'Place liked',
          'Your swipe was saved, but Adventour could not add this place as a trip stop yet.',
        );
      }
    }
  };

  const fetchSuggestions = async (input: string, biasLocation: Coordinates | null = currentCoords) => {
    if (autocompleteTimer.current) {
      clearTimeout(autocompleteTimer.current);
    }

    if (input.length <= 2) {
      setSuggestions([]);
      return;
    }

    autocompleteTimer.current = setTimeout(async () => {
      const autocompleteSuggestions = await GoogleAutocompleteService.fetchAutocompleteSuggestions(
        input,
        biasLocation,
        radiusOption.meters,
      );
      setSuggestions(autocompleteSuggestions);
    }, 350);
  };

  const fetchOriginSuggestions = async (input: string) => {
    if (originAutocompleteTimer.current) {
      clearTimeout(originAutocompleteTimer.current);
    }

    if (input.length <= 2) {
      setOriginSuggestions([]);
      return;
    }

    originAutocompleteTimer.current = setTimeout(async () => {
      const autocompleteSuggestions = await GoogleAutocompleteService.fetchAutocompleteSuggestions(
        input,
        null,
        radiusOption.meters,
      );
      setOriginSuggestions(autocompleteSuggestions);
    }, 350);
  };

  const handleCityChange = (text: string) => {
    setCity(text);
    setLocationMode(text.trim() ? 'manual' : 'none');
    setCurrentCoords(null);
    fetchSuggestions(text, null);
  };

  const handleTripOriginChange = (text: string) => {
    setTripOrigin(text);
    setItineraryPlan(null);
    fetchOriginSuggestions(text);
  };

  const handleSuggestionSelect = async (description: string) => {
    setCity(description);
    setLocationMode('manual');
    setCurrentCoords(null);
    setSuggestions([]);

    try {
      const geocodeResponse = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
        params: { address: description },
      });
      const resolvedLocation = {
        latitude: Number(geocodeResponse.data.latitude),
        longitude: Number(geocodeResponse.data.longitude),
      };
      if (Number.isFinite(resolvedLocation.latitude) && Number.isFinite(resolvedLocation.longitude)) {
        setCurrentCoords(resolvedLocation);
      }
    } catch (error) {
      console.error('Error resolving selected launch point:', describeAxiosError(error));
    }
  };

  const handleOriginSuggestionSelect = (description: string) => {
    setTripOrigin(description);
    setOriginSuggestions([]);
    setItineraryPlan(null);
  };

  const loadLocalEventPreview = useCallback(async (
    location: Coordinates,
    preferenceTags: string[] = [],
    quiet = true,
  ) => {
    setLocalEventsLoading(true);
    try {
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/local-events/recommendations`, {
        location,
        radius_meters: radiusOption.meters,
        destination_label: city || 'your launch point',
        limit: 4,
        preference_tags: preferenceTags,
        member_ids: selectedFriendIds,
      });
      setLocalEventPreview(response.data);
    } catch (error) {
      console.error('Error loading local event preview:', describeAxiosError(error));
      if (!quiet) {
        Alert.alert('Events not ready', 'Adventour could not load local events for this launch point yet.');
      }
    } finally {
      setLocalEventsLoading(false);
    }
  }, [city, radiusOption.meters, selectedFriendIds]);

  const loadRecommendations = useCallback(async ({
    append = false,
    quiet = false,
    boostQueryTags,
    scoringProfileOverride,
    radiusOptionOverride,
    excludedTagGroupsOverride,
  }: {
    append?: boolean;
    quiet?: boolean;
    boostQueryTags?: string[];
    scoringProfileOverride?: ScoringProfileOption;
    radiusOptionOverride?: RadiusOption;
    excludedTagGroupsOverride?: string[];
  } = {}) => {
    const activeBoostQueryTags = boostQueryTags ?? boostedFriendQueryTags;
    const activeScoringProfile = scoringProfileOverride || scoringProfile;
    const activeRadiusOption = radiusOptionOverride || radiusOption;
    const activeExcludedTagGroups = excludedTagGroupsOverride ?? excludedTagGroups;
    const activeAutoScoutSelected = activeScoringProfile.id === 'auto_scout';
    if (append) {
      if (autoRefillInFlight.current) {
        return;
      }
      autoRefillInFlight.current = true;
      setLoadingMore(true);
    } else {
      setLoading(true);
      setPlaces([]);
      setHasLoadedRecommendations(false);
      setAutoRefillAvailable(false);
      setGroupFitSummary(null);
      setSlateSummary(null);
      setRecommendationQuality(null);
      setBasketScenarioReadiness(null);
      setRecommendationFilterSummary(null);
      setRetrievalContext(null);
      setSessionContext(null);
      setBasketComparisons([]);
      setRecommendedBasketProfile(null);
      setBasketProviderUsage(null);
      setLocalEventPreview(null);
      recentlyDecidedPlaceIds.current.clear();
    }
    setEmptyMessage(append ? 'Scouting more recommendations...' : 'Loading recommendations...');

    let step: RequestStep = 'recommendations';

    try {
      let recommendationPayload: any;
      let eventLookupLocation: Coordinates | null = null;
      const recommendationRequestPayload = (location: Coordinates) => ({
        mode: 'spontaneous',
        location,
        radius_meters: activeRadiusOption.meters,
        member_ids: selectedFriendIds,
        constraints: {
          limit: 20,
          avoid_chains: true,
          scoring_profile: backendScoringProfileId(activeScoringProfile),
          ...(activeScoringProfile.learnedRerank ? { learned_rerank: true } : {}),
          excluded_tag_groups: activeExcludedTagGroups,
          time_context: recommendationTimeContext(),
          ...(activeBoostQueryTags.length ? { boost_query_tags: activeBoostQueryTags } : {}),
        },
      });
      const requestRecommendations = async (location: Coordinates) => axios.post(
        `${Config.BACKEND_BASE_URL}/api/recommendations`,
        recommendationRequestPayload(location),
      );
      const requestComparedRecommendations = async (location: Coordinates) => axios.post(
        `${Config.BACKEND_BASE_URL}/api/recommendations/compare`,
        {
          ...recommendationRequestPayload(location),
          scoring_profiles: autoScoutComparisonOptions.map((option) => option.id),
          include_recommendations: true,
        },
      );
      const requestBestBasket = async (location: Coordinates) => {
        if (append || activeScoringProfile.learnedRerank || !activeAutoScoutSelected) {
          if (!append) {
            setBasketComparisons([]);
            setRecommendedBasketProfile(null);
            setBasketProviderUsage(null);
          }
          const response = await requestRecommendations(location);
          return response.data;
        }

        try {
          const comparisonResponse = await requestComparedRecommendations(location);
          const comparisons: BasketComparison[] = comparisonResponse.data.comparisons || [];
          const recommendedProfile = comparisonResponse.data.recommended_profile || comparisons[0]?.scoring_profile || null;
          const winningComparison = comparisons.find((comparison) => comparison.scoring_profile === recommendedProfile) || comparisons[0];
          const winningResult = winningComparison?.result || {
            recommendations: winningComparison?.recommendations || [],
            recommendation_quality: winningComparison?.recommendation_quality,
            scenario_readiness: winningComparison?.scenario_readiness,
            group_fit_summary: winningComparison?.group_fit_summary,
            slate_summary: winningComparison?.slate_summary,
            filter_summary: winningComparison?.result?.filter_summary,
            retrieval_context: winningComparison?.result?.retrieval_context,
            session_context: winningComparison?.result?.session_context,
          };
          setBasketComparisons(comparisons);
          setRecommendedBasketProfile(recommendedProfile);
          setBasketProviderUsage(comparisonResponse.data.provider_usage || null);

          if (winningResult?.recommendations?.length) {
            return {
              ...winningResult,
              scoring_profile: winningComparison?.scoring_profile,
              recommendation_quality: winningComparison?.recommendation_quality || winningResult.recommendation_quality,
              scenario_readiness: winningComparison?.scenario_readiness || winningResult.scenario_readiness,
              group_fit_summary: winningComparison?.group_fit_summary || winningResult.group_fit_summary,
              slate_summary: winningComparison?.slate_summary || winningResult.slate_summary,
              filter_summary: winningResult.filter_summary,
              retrieval_context: winningResult.retrieval_context,
              session_context: winningResult.session_context,
            };
          }
        } catch (compareError) {
          console.error('Error comparing basket scout styles:', describeAxiosError(compareError));
          setBasketComparisons([]);
          setRecommendedBasketProfile(null);
          setBasketProviderUsage(null);
        }

        const response = await requestRecommendations(location);
        return response.data;
      };

      if (locationMode === 'gps' && currentCoords) {
        step = 'recommendations';
        console.log('Finding places using GPS coordinates:', currentCoords);
        recommendationPayload = await requestBestBasket(currentCoords);
        eventLookupLocation = currentCoords;
      } else if (locationMode === 'manual' && currentCoords) {
        step = 'recommendations';
        console.log('Finding places using saved manual destination:', currentCoords);
        recommendationPayload = await requestBestBasket(currentCoords);
        eventLookupLocation = currentCoords;
      } else if (city.trim()) {
        step = 'geocode';
        console.log('Resolving manual destination:', city.trim());
        const geocodeResponse = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
          params: { address: city.trim() },
        });
        const resolvedLocation = {
          latitude: Number(geocodeResponse.data.latitude),
          longitude: Number(geocodeResponse.data.longitude),
        };
        if (!Number.isFinite(resolvedLocation.latitude) || !Number.isFinite(resolvedLocation.longitude)) {
          throw new Error(`Unable to resolve coordinates for ${city}`);
        }
        setCurrentCoords(resolvedLocation);
        setLocationMode('manual');
        step = 'recommendations';
        console.log('Finding places using resolved destination:', resolvedLocation);
        recommendationPayload = await requestBestBasket(resolvedLocation);
        eventLookupLocation = resolvedLocation;
      } else {
        if (!quiet) {
          Alert.alert('Error', 'Please enter a location or enable GPS.');
        }
        return;
      }

      const recommendations = recommendationPayload.recommendations || [];
      setPreferenceInsights(recommendationPayload.preference_insights || []);
      setGroupFitSummary(recommendationPayload.group_fit_summary || null);
      setSlateSummary(recommendationPayload.slate_summary || null);
      setRecommendationQuality(recommendationPayload.recommendation_quality || null);
      setBasketScenarioReadiness(recommendationPayload.scenario_readiness || null);
      setRecommendationFilterSummary(recommendationPayload.filter_summary || null);
      setRetrievalContext(recommendationPayload.retrieval_context || null);
      setSessionContext(recommendationPayload.session_context || null);
      if (recommendationPayload.learned_rerank?.reason && recommendationPayload.learned_rerank.reason !== 'not_enabled') {
        setLearnedRerankSummary(recommendationPayload.learned_rerank);
      }
      if (!append && eventLookupLocation) {
        const eventTags = Array.from(new Set([
          ...(Array.isArray(recommendationPayload.query_tags) ? recommendationPayload.query_tags : []),
          ...(Array.isArray(recommendationPayload.intent_target_groups) ? recommendationPayload.intent_target_groups : []),
          ...topTasteTags.map((tag) => tag.tag),
          ...(selectedTagGroup !== 'all' ? [selectedTagGroup] : []),
        ].filter((tag) => (
          typeof tag === 'string'
          && tag.trim().length > 0
          && !activeExcludedTagGroups.includes(tag)
        )))).slice(0, 8);
        loadLocalEventPreview(
          eventLookupLocation,
          eventTags,
          true,
        );
      }
      const results = recommendations
        .map(placeFromRecommendation)
        .filter((place: Place) => (
          !recentlyDecidedPlaceIds.current.has(place.place_id)
          && (!place.provider_place_id || !recentlyDecidedPlaceIds.current.has(String(place.provider_place_id)))
        ));

      const existingIds = new Set(
        places.flatMap((place) => [
          place.place_id,
          place.provider_place_id ? String(place.provider_place_id) : '',
        ]).filter(Boolean),
      );
      const freshResults = append
        ? results.filter((place: Place) => (
          !existingIds.has(place.place_id)
          && (!place.provider_place_id || !existingIds.has(String(place.provider_place_id)))
        ))
        : results;

      setPlaces(append ? [...places, ...freshResults] : freshResults);
      setHasLoadedRecommendations((current) => current || freshResults.length > 0 || append);
      setAutoRefillAvailable(!append || freshResults.length > 0);
      if (!append) {
        setSelectedTagGroup('all');
        pendingBasketScroll.current = freshResults.length > 0;
      }
      if (freshResults.length > 0 || append) {
        setEmptyMessage(freshResults.length > 0 ? '' : 'No new places found yet. Try refreshing or widening the search distance.');
      } else {
        const providerErrors = recommendationPayload.provider_errors || [];
        const hasProviderErrors = providerErrors.length > 0;
        const fallbackMessage = hasProviderErrors
          ? 'No places found because the place provider lookup failed.'
          : 'No places found for this search. Try a wider distance or a different location.';
        const message = emptyMessageFromFilterSummary(
          recommendationPayload.filter_summary,
          fallbackMessage,
        );
        setEmptyMessage(message);
        setHasLoadedRecommendations(false);
      }
    } catch (error: unknown) {
      const details = describeAxiosError(error);
      console.error(`Error during ${step}:`, details);
      const message = step === 'geocode'
        ? 'Unable to resolve that destination. Try a more specific city, state, or address.'
        : 'Unable to load recommendations for that destination.';
      setEmptyMessage(message);
      if (!append) {
        setHasLoadedRecommendations(false);
      }
      setAutoRefillAvailable(false);
      if (!quiet) {
        Alert.alert('Error', message);
      }
    } finally {
      if (append) {
        setLoadingMore(false);
        autoRefillInFlight.current = false;
      } else {
        setLoading(false);
      }
    }
  }, [
    backendBaseURL,
    autoScoutComparisonOptions,
    boostedFriendQueryTags,
    city,
    currentCoords,
    excludedTagGroups,
    loadLocalEventPreview,
    locationMode,
    places,
    radiusOption.meters,
    scoringProfile.id,
    scoringProfile.learnedRerank,
    selectedFriendIds,
    selectedTagGroup,
    topTasteTags,
  ]);

  const handleFindPlaces = () => {
    loadRecommendations({ append: false });
  };

  const handleRecommendationDeckExhausted = useCallback(() => {
    loadRecommendations({ append: true, quiet: true });
  }, [loadRecommendations]);

  const applyFriendSuggestionTag = useCallback((tag: string) => {
    const normalized = tag.trim();
    if (!normalized) {
      return;
    }

    const nextTags = Array.from(new Set([normalized, ...boostedFriendQueryTags])).slice(0, 4);
    setBoostedFriendQueryTags(nextTags);
    loadRecommendations({ append: false, boostQueryTags: nextTags });
  }, [boostedFriendQueryTags, loadRecommendations]);

  const applyRecommendationRepair = useCallback((adjustment?: RemediationAdjustment) => {
    if (!adjustment) {
      return;
    }

    if (adjustment.kind === 'collect_feedback') {
      setFiltersOpen(false);
      scrollRef.current?.scrollTo({
        y: Math.max(0, basketOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind === 'collect_trip_inputs') {
      setFiltersOpen(false);
      scrollRef.current?.scrollTo({
        y: Math.max(0, tripDetailsOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind === 'scout_local_events' || adjustment.kind === 'collect_event_social_signal') {
      setFiltersOpen(false);
      setEventDraftOpen(adjustment.kind === 'collect_event_social_signal');
      scrollRef.current?.scrollTo({
        y: Math.max(0, eventSectionOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind === 'collect_booking_details') {
      setFiltersOpen(false);
      scrollRef.current?.scrollTo({
        y: Math.max(0, bookingSectionOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind !== 'rerun_recommendations') {
      return;
    }

    const nextScoringProfile = scoutStyleForId(adjustment.scoring_profile) || scoringProfile;
    const nextRadiusOption = radiusOptionForMultiplier(radiusOption, adjustment.radius_multiplier);
    const nextExcludedTagGroups = adjustment.clear_excluded_tag_groups ? [] : excludedTagGroups;
    const nextBoostedTags = adjustment.boost_query_tags?.length
      ? Array.from(new Set([...adjustment.boost_query_tags, ...boostedFriendQueryTags])).slice(0, 4)
      : boostedFriendQueryTags;

    setScoringProfile(nextScoringProfile);
    setRadiusOption(nextRadiusOption);
    setExcludedTagGroups(nextExcludedTagGroups);
    setBoostedFriendQueryTags(nextBoostedTags);
    setSelectedTagGroup('all');
    setFiltersOpen(false);
    loadRecommendations({
      append: false,
      boostQueryTags: nextBoostedTags,
      scoringProfileOverride: nextScoringProfile,
      radiusOptionOverride: nextRadiusOption,
      excludedTagGroupsOverride: nextExcludedTagGroups,
    });
  }, [
    basketOffsetY,
    boostedFriendQueryTags,
    bookingSectionOffsetY,
    excludedTagGroups,
    loadRecommendations,
    eventSectionOffsetY,
    radiusOption,
    scoringProfile,
    tripDetailsOffsetY,
  ]);

  const applyItineraryRepair = useCallback((adjustment?: RemediationAdjustment) => {
    if (!adjustment) {
      return;
    }

    if (adjustment.kind === 'collect_trip_inputs') {
      setFiltersOpen(false);
      scrollRef.current?.scrollTo({
        y: Math.max(0, tripDetailsOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind === 'scout_local_events' || adjustment.kind === 'collect_event_social_signal') {
      setFiltersOpen(false);
      setEventDraftOpen(adjustment.kind === 'collect_event_social_signal');
      scrollRef.current?.scrollTo({
        y: Math.max(0, eventSectionOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind === 'collect_booking_details') {
      setFiltersOpen(false);
      scrollRef.current?.scrollTo({
        y: Math.max(0, bookingSectionOffsetY - 12),
        animated: true,
      });
      return;
    }

    if (adjustment.kind !== 'rerun_recommendations') {
      return;
    }

    const nextScoringProfile = scoutStyleForId(adjustment.scoring_profile) || scoringProfile;
    const nextRadiusOption = radiusOptionForMultiplier(radiusOption, adjustment.radius_multiplier);
    const nextExcludedTagGroups = adjustment.clear_excluded_tag_groups ? [] : excludedTagGroups;
    const nextBoostedTags = adjustment.boost_query_tags?.length
      ? Array.from(new Set([...adjustment.boost_query_tags, ...boostedFriendQueryTags])).slice(0, 4)
      : boostedFriendQueryTags;

    setScoringProfile(nextScoringProfile);
    setRadiusOption(nextRadiusOption);
    setExcludedTagGroups(nextExcludedTagGroups);
    setBoostedFriendQueryTags(nextBoostedTags);
    setSelectedTagGroup('all');
    setFiltersOpen(false);
    loadItineraryPlan({
      scoringProfileOverride: nextScoringProfile,
      radiusOptionOverride: nextRadiusOption,
      excludedTagGroupsOverride: nextExcludedTagGroups,
      boostQueryTagsOverride: nextBoostedTags,
    });
  }, [
    boostedFriendQueryTags,
    bookingSectionOffsetY,
    excludedTagGroups,
    loadItineraryPlan,
    eventSectionOffsetY,
    radiusOption,
    scoringProfile,
    tripDetailsOffsetY,
  ]);

  const requestLocationPermission = async () => {
    if (Platform.OS === 'android') {
      const granted = await PermissionsAndroid.request(
        PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION,
        {
          title: "Location Permission",
          message: "Adventour needs access to your location.",
          buttonPositive: "OK"
        }
      );
      return granted === PermissionsAndroid.RESULTS.GRANTED;
    }
    return true;
  };

  const useCurrentLocation = async () => {
    const granted = await requestLocationPermission();
    if (!granted) {
      Alert.alert("Permission Denied", "Location access is required.");
      return;
    }

    Geolocation.getCurrentPosition(
      async (position) => {
        const { latitude, longitude } = position.coords;
        setCurrentCoords({ latitude, longitude });
        setLocationMode('gps');

        try {
          const response = await axios.get(`${Config.BACKEND_BASE_URL}/geocode`, {
            params: { latitude, longitude },
          });

          const { city, state } = response.data;
          if (city && state) {
            setCity(`${city}, ${state}`);
          } else {
            Alert.alert('Error', 'Unable to resolve location to a city and state.');
          }
        } catch (error) {
          console.error('Error fetching geocoded location:', error);
          setCity(`${latitude.toFixed(4)}, ${longitude.toFixed(4)}`);
        }
      },
      (error) => {
        console.error('Geolocation error:', error);
        Alert.alert("Location Error", error.message);
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 10000 }
    );
  };

  const itineraryPlaceName = itineraryRecommendationName;

  const itineraryPlaceAddress = (item?: ItineraryRecommendation) =>
    item?.display?.vicinity || 'Address available after opening details';

  const routeGroupLabel = (group: string) => ({
    food_drink: 'Food & drink',
    arts_culture: 'Arts & culture',
    outdoors: 'Outdoors',
    shopping_market: 'Markets',
    nightlife: 'Nightlife',
    other: 'Local finds',
  }[group] || group.replace(/_/g, ' '));

  const routeGroupTone = (group: string) => ({
    food_drink: '#e6534b',
    arts_culture: '#123c69',
    outdoors: '#134e4a',
    shopping_market: '#9a3412',
    nightlife: '#4c1d95',
    other: '#31506b',
  }[group] || '#31506b');

  const formatFitPercent = (value?: number | null) => (
    value === undefined || value === null ? '0%' : `${Math.round(value * 100)}%`
  );

  const stopReasonMetrics = (reasoning?: ItineraryStop['why_this_stop']) => {
    const stats = reasoning?.stats || {};
    return [
      typeof stats.route_score === 'number'
        ? { id: 'route', label: 'Route', value: formatFitPercent(stats.route_score) }
        : null,
      typeof stats.authenticity === 'number'
        ? { id: 'local', label: 'Local', value: formatFitPercent(stats.authenticity) }
        : null,
      typeof stats.hidden_gem_score === 'number'
        ? { id: 'gem', label: 'Gem', value: formatFitPercent(stats.hidden_gem_score) }
        : null,
      typeof stats.member_fit === 'number'
        ? { id: 'party', label: 'Party', value: formatFitPercent(stats.member_fit) }
        : null,
      typeof stats.friend_history_fit === 'number' && stats.friend_history_fit !== 0
        ? { id: 'friend-history', label: 'Friend', value: formatFitPercent(stats.friend_history_fit) }
        : null,
    ].filter((metric): metric is { id: string; label: string; value: string } => Boolean(metric));
  };

  const formatEventDate = (value?: string) => {
    if (!value) {
      return 'Date coming soon';
    }
    return new Date(value).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  const formatEventDistance = (meters?: number) => {
    if (typeof meters !== 'number') {
      return null;
    }
    if (meters < 1000) {
      return `${Math.max(1, Math.round(meters))} m away`;
    }
    const miles = meters / 1609.344;
    return `${miles.toFixed(miles >= 10 ? 0 : 1)} mi away`;
  };

  const formatEventPrice = (low?: number, high?: number) => {
    if (typeof low !== 'number' && typeof high !== 'number') {
      return null;
    }
    if (typeof low === 'number' && typeof high === 'number') {
      return low === high ? `$${low}` : `$${low}-${high}`;
    }
    return typeof low === 'number' ? `From $${low}` : `Up to $${high}`;
  };

  const eventSocialLabel = (event: LocalEventRecommendation) => {
    const friendGoing = event.social?.friend_going_count || 0;
    const friendInterested = event.social?.friend_interested_count || 0;
    const friendParts = [
      friendGoing ? `${friendGoing} friend${friendGoing === 1 ? '' : 's'} going` : '',
      friendInterested ? `${friendInterested} friend${friendInterested === 1 ? '' : 's'} interested` : '',
    ].filter(Boolean);
    if (friendParts.length) {
      return friendParts.join(' - ');
    }

    const going = event.social?.going_count || 0;
    const interested = event.social?.interested_count || 0;
    const parts = [
      going ? `${going} going` : '',
      interested ? `${interested} interested` : '',
    ].filter(Boolean);
    return parts.length ? parts.join(' - ') : 'Be the first to mark interest';
  };

  const eventFriendPreviewLabel = (event: LocalEventRecommendation) => {
    const preview = event.social?.friend_preview || [];
    if (preview.length) {
      return preview
        .slice(0, 3)
        .map((friend) => `${friend.display_name} ${friend.status === 'going' ? 'is going' : 'is interested'}`)
        .join(' - ');
    }

    if (event.social?.social_next_action) {
      return event.social.social_next_action;
    }

    const candidates = (event.social?.friend_candidates || [])
      .filter((friend) => !friend.status)
      .slice(0, 3);
    if (!candidates.length) {
      return null;
    }
    return `Ask ${candidates.map((friend) => friend.display_name).join(', ')} to react.`;
  };

  const parseLocalEventDate = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const normalized = trimmed.includes('T')
      ? trimmed
      : trimmed.replace(' ', 'T');
    const parsed = new Date(normalized);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  };

  const refreshLocalEvents = async () => {
    if (!currentCoords) {
      return;
    }
    try {
      const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/local-events/recommendations`, {
        location: currentCoords,
        radius_meters: radiusOption.meters,
        destination_label: itineraryPlan?.destination || city,
        limit: 6,
        travel_dates: itineraryPlan?.booking_plan?.travel_dates,
        preference_tags: itineraryPlan?.query_tags || [],
        member_ids: selectedFriendIds,
      });
      setItineraryPlan((current) => {
        if (!current) {
          return current;
        }
        const nextPlan: ItineraryPlan = {
          ...current,
          local_events: response.data,
        };
        nextPlan.local_events = localEventsForItineraryPlan(nextPlan);
        nextPlan.route_readiness = routeReadinessForItineraryPlan(nextPlan);
        nextPlan.route_explanation = routeExplanationForItineraryPlan(nextPlan);
        nextPlan.launch_checklist = launchChecklistForItineraryPlan(nextPlan);
        nextPlan.scenario_readiness = scenarioReadinessForItineraryPlan(nextPlan);
        nextPlan.itinerary_story = itineraryStoryForItineraryPlan(nextPlan);
        nextPlan.swap_guide = swapGuideForItineraryPlan(nextPlan);
        nextPlan.route_model_confidence = routeModelConfidenceForItineraryPlan(nextPlan);
        nextPlan.trip_packet = tripPacketForItineraryPlan(nextPlan);
        return withSwapSummary(nextPlan);
      });
      setLocalEventPreview(response.data);
    } catch (error) {
      console.error('Error refreshing local events:', describeAxiosError(error));
    }
  };

  const submitLocalEvent = async () => {
    const startsAt = parseLocalEventDate(eventDraft.starts_at);
    if (!eventDraft.title.trim() || !startsAt) {
      Alert.alert('Event needs a title and date', 'Use a date like 2026-07-18 19:30.');
      return;
    }

    setEventSaving(true);
    try {
      await axios.post(`${Config.BACKEND_BASE_URL}/api/local-events`, {
        title: eventDraft.title.trim(),
        starts_at: startsAt,
        category: eventDraft.category.trim() || 'community',
        description: eventDraft.description.trim() || undefined,
        source_name: 'Adventour community',
        source_url: eventDraft.source_url.trim() || undefined,
        reservation_url: eventDraft.reservation_url.trim() || undefined,
        city: city || itineraryPlan?.destination,
        latitude: currentCoords?.latitude,
        longitude: currentCoords?.longitude,
      });
      setEventDraft({
        title: '',
        starts_at: '',
        category: '',
        description: '',
        source_url: '',
        reservation_url: '',
      });
      setEventDraftOpen(false);
      await refreshLocalEvents();
    } catch (error) {
      console.error('Error submitting local event:', describeAxiosError(error));
      Alert.alert('Could not add event', 'Check the date and links, then try again.');
    } finally {
      setEventSaving(false);
    }
  };

  const applyLocalEventSocial = (
    eventId: number,
    social: LocalEventRecommendation['social'],
  ) => {
    const updateEventsPayload = (current: LocalEventsPayload | undefined | null): LocalEventsPayload | undefined | null => {
      if (!current?.events) {
        return current;
      }
      const nextEvents = current.events.map((event) => (
        event.id === eventId
          ? {
              ...event,
              social: {
                ...(event.social || {}),
                ...(social || {}),
              },
            }
          : event
      ));
      return {
        ...current,
        events: nextEvents,
        summary: current.summary
          ? {
              ...current.summary,
              interested_count: nextEvents.reduce((total, event) => total + (event.social?.interested_count || 0), 0),
              going_count: nextEvents.reduce((total, event) => total + (event.social?.going_count || 0), 0),
              friend_interested_count: nextEvents.reduce((total, event) => total + (event.social?.friend_interested_count || 0), 0),
              friend_going_count: nextEvents.reduce((total, event) => total + (event.social?.friend_going_count || 0), 0),
              social_readiness: socialReadinessForLocalEvents(nextEvents, current.summary.social_readiness),
            }
          : current.summary,
      };
    };

    setLocalEventPreview((current) => updateEventsPayload(current) || null);
    setItineraryPlan((current) => {
      if (!current?.local_events?.events) {
        return current;
      }
      const nextPlan: ItineraryPlan = {
        ...current,
        local_events: updateEventsPayload(current.local_events) || current.local_events,
      };
      nextPlan.local_events = localEventsForItineraryPlan(nextPlan);
      nextPlan.route_readiness = routeReadinessForItineraryPlan(nextPlan);
      nextPlan.route_explanation = routeExplanationForItineraryPlan(nextPlan);
      nextPlan.launch_checklist = launchChecklistForItineraryPlan(nextPlan);
      nextPlan.scenario_readiness = scenarioReadinessForItineraryPlan(nextPlan);
      nextPlan.itinerary_story = itineraryStoryForItineraryPlan(nextPlan);
      nextPlan.swap_guide = swapGuideForItineraryPlan(nextPlan);
      nextPlan.route_model_confidence = routeModelConfidenceForItineraryPlan(nextPlan);
      nextPlan.trip_packet = tripPacketForItineraryPlan(nextPlan);
      return {
        ...withSwapSummary(nextPlan),
      };
    });
  };

  const setLocalEventInterest = async (
    event: LocalEventRecommendation,
    status: 'interested' | 'going',
  ) => {
    const currentStatus = event.social?.viewer_status;
    const removing = currentStatus === status;

    try {
      if (removing) {
        const response = await axios.delete(`${Config.BACKEND_BASE_URL}/api/local-events/${event.id}/interest`);
        applyLocalEventSocial(event.id, response.data.social);
      } else {
        const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/local-events/${event.id}/interest`, { status });
        applyLocalEventSocial(event.id, response.data.social);
      }
    } catch (error) {
      console.error('Error updating local event interest:', describeAxiosError(error));
      Alert.alert('Could not update event', 'Try again in a moment.');
    }
  };

  const reservationTypeForComponent = (component: BookingComponent) => (
    component.type === 'event_or_place' ? 'place' : component.type
  );

  const reservationTypeForBookingLink = (link: BookingActionLink) => {
    if (link.reservation_type) {
      return link.reservation_type;
    }
    return link.component_type === 'event_or_place' ? 'place' : (link.component_type || 'other');
  };

  const bookingStatusLabel = (status: string) => {
    if (status === 'estimated') {
      return 'Estimate';
    }
    if (status === 'ready_for_provider') {
      return 'Ready to quote';
    }
    if (status === 'optional_for_day_trip' || status === 'not_needed_for_day_trip') {
      return 'Optional';
    }
    if (status === 'manual_or_link_out') {
      return 'Manual';
    }
    return 'Connect later';
  };

  const formatRouteDistance = (meters?: number | null) => {
    if (!meters) {
      return 'Distance estimated after route details are available';
    }
    const miles = meters / 1609.344;
    return `${miles.toFixed(miles >= 10 ? 0 : 1)} mi planned between stops`;
  };

  const preferredProviderOption = (component: BookingComponent) => (
    component.provider_options?.find((option) => option.url)
    || component.provider_options?.[0]
    || null
  );

  const openReservationDraft = (component: BookingComponent) => {
    const providerOption = preferredProviderOption(component);
    setReservationDraft({
      reservation_type: reservationTypeForComponent(component),
      title: `${component.label} for ${itineraryPlan?.destination || city || 'Adventour'}`,
      provider: providerOption?.label || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: providerOption?.url || '',
      notes: [
        component.action || '',
        providerOption?.note ? `Provider note: ${providerOption.note}` : '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openReservationDraftFromBookingLink = (link: BookingActionLink) => {
    const destinationLabel = itineraryPlan?.destination || city || 'Adventour';
    setReservationDraft({
      reservation_type: reservationTypeForBookingLink(link),
      title: link.draft_title
        ? `${link.draft_title} for ${destinationLabel}`
        : `${link.label || 'Booking'} for ${destinationLabel}`,
      provider: link.draft_provider || link.provider_label || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: link.draft_booking_url || link.url || '',
      notes: link.draft_notes || [
        link.note || '',
        link.search_hint ? `Search hint: ${link.search_hint}` : '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openEventReservationDraft = (event: LocalEventRecommendation) => {
    setReservationDraft({
      reservation_type: 'event',
      title: event.title,
      provider: event.source_name || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: event.reservation_url || event.source_url || '',
      notes: [
        event.starts_at ? `Event time: ${formatEventDate(event.starts_at)}` : '',
        event.description || '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openReservationDraftFromTripPrompt = (prompt: NonNullable<TripPacket['save_prompts']>[number]) => {
    const routeContext = prompt.route_context;
    setReservationDraft({
      reservation_type: prompt.reservation_type || 'other',
      title: (prompt.label || 'Adventour booking detail').replace(/^RSVP:\s*/i, ''),
      provider: prompt.provider || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: prompt.reservation_url || prompt.source_url || '',
      notes: [
        prompt.starts_at ? `Event time: ${formatEventDate(prompt.starts_at)}` : '',
        routeContext?.fit_label ? `Route pairing: ${routeContext.fit_label}${routeContext.day ? ` on day ${routeContext.day}` : ''}` : '',
        prompt.detail || '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openReservationDraftFromMobilitySetup = (mobility: NonNullable<TripPacket['mobility_setup']>) => {
    const destinationLabel = itineraryPlan?.destination || city || 'Adventour';
    const estimate = mobility.estimate;
    const estimateLine = estimate
      && typeof estimate.per_person_low === 'number'
      && typeof estimate.per_person_high === 'number'
      ? `${estimate.currency || 'USD'} $${estimate.per_person_low}-${estimate.per_person_high} per person`
      : '';
    setReservationDraft({
      reservation_type: mobility.reservation_type || 'local_transport',
      title: mobility.draft_title || `${mobility.provider_label || mobility.label || 'Local travel'} for ${destinationLabel}`,
      provider: mobility.draft_provider || mobility.provider || mobility.provider_label || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: mobility.draft_booking_url || mobility.source_url || '',
      notes: mobility.draft_notes || [
        mobility.next_step || '',
        mobility.recommended_option?.label ? `Recommended option: ${mobility.recommended_option.label}` : '',
        mobility.recommended_option?.why || '',
        estimateLine ? `Estimate: ${estimateLine}` : '',
        mobility.route_distance_meters ? `Route distance: ${formatRouteDistance(mobility.route_distance_meters)}` : '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openReservationDraftFromTripCommand = (
    command: NonNullable<NonNullable<TripPacket['booking_command_center']>['commands']>[number],
  ) => {
    const destinationLabel = itineraryPlan?.destination || city || 'Adventour';
    setReservationDraft({
      reservation_type: command.reservation_type || command.component_type || 'other',
      title: `${command.label || 'Booking detail'} for ${destinationLabel}`,
      provider: command.provider_label || '',
      confirmation_code: '',
      cost_total: '',
      booking_url: command.source_url || '',
      notes: [
        command.action || '',
        command.detail || '',
        command.phase ? `Booking phase: ${command.phase}` : '',
      ].filter(Boolean).join('\n'),
    });
  };

  const openExistingReservationDraft = (reservation: TravelReservation) => {
    setReservationDraft({
      id: reservation.id,
      reservation_type: reservation.reservation_type,
      title: reservation.title || '',
      provider: reservation.provider || '',
      confirmation_code: reservation.confirmation_code || '',
      cost_total: reservation.cost_total != null ? String(reservation.cost_total) : '',
      booking_url: reservation.booking_url || '',
      notes: reservation.notes || '',
    });
  };

  const applyReservationResponseAdventour = (adventour?: AdventourSession | null) => {
    if (!adventour) {
      return;
    }
    setActiveAdventour((current) => (
      current?.id === adventour.id ? adventour : current
    ));
  };

  const saveReservationDraft = async () => {
    if (!reservationDraft || !reservationDraft.title.trim()) {
      Alert.alert('Add a title', 'Give this booking detail a name before saving it.');
      return;
    }

    setReservationSaving(true);
    try {
      const payload: Record<string, any> = {
        reservation_type: reservationDraft.reservation_type,
        title: reservationDraft.title.trim(),
        provider: reservationDraft.provider.trim() || undefined,
        confirmation_code: reservationDraft.confirmation_code.trim() || undefined,
        cost_total: reservationDraft.cost_total.trim() || undefined,
        booking_url: reservationDraft.booking_url.trim() || undefined,
        notes: reservationDraft.notes.trim() || undefined,
      };

      const response = reservationDraft.id
        ? await axios.patch(`${Config.BACKEND_BASE_URL}/api/reservations/${reservationDraft.id}`, payload)
        : await axios.post(`${Config.BACKEND_BASE_URL}/api/reservations`, {
          ...payload,
          adventour_session_id: activeAdventour?.id,
          metadata: {
            source: 'discover_itinerary_plan',
            destination: itineraryPlan?.destination || city,
          },
        });
      const savedReservation = response.data.reservation;
      setSavedReservations((current) => (
        reservationDraft.id
          ? current.map((item) => (item.id === savedReservation.id ? savedReservation : item))
          : [savedReservation, ...current]
      ));
      applyReservationResponseAdventour(response.data.adventour);
      if (!reservationDraft.id && !activeAdventour?.id && itineraryPlan && savedReservation?.id && !savedReservation?.adventour_session_id) {
        setPendingItineraryReservationIds((current) => (
          current.includes(savedReservation.id) ? current : [...current, savedReservation.id]
        ));
      }
      setReservationDraft(null);
    } catch (error) {
      console.error('Error saving reservation:', describeAxiosError(error));
      Alert.alert('Could not save details', 'Check the cost format and try again.');
    } finally {
      setReservationSaving(false);
    }
  };

  const deleteReservation = async (reservationId: number) => {
    try {
      const response = await axios.delete(`${Config.BACKEND_BASE_URL}/api/reservations/${reservationId}`);
      setSavedReservations((current) => current.filter((item) => item.id !== reservationId));
      setPendingItineraryReservationIds((current) => current.filter((id) => id !== reservationId));
      applyReservationResponseAdventour(response.data.adventour);
    } catch (error) {
      console.error('Error deleting reservation:', describeAxiosError(error));
      Alert.alert('Could not remove details', 'Try again in a moment.');
    }
  };

  const renderBookingPlan = () => {
    const itineraryPlanWithReservationCoverage = itineraryPlan
      ? withReservationCoverage(itineraryPlan, itinerarySavedReservations)
      : null;
    const bookingPlan = itineraryPlanWithReservationCoverage?.booking_plan || itineraryPlan?.booking_plan;
    const components = bookingPlan?.components || [];
    if (!bookingPlan || !components.length) {
      return null;
    }
    const currency = itineraryPlan?.price_breakdown?.currency || 'USD';
    const bookingSummary = bookingPlan.summary || itineraryPlan?.route_readiness?.booking_summary;
    const bookingReadinessLabel = typeof bookingSummary?.readiness_score === 'number'
      ? `${Math.round(bookingSummary.readiness_score * 100)}% ready`
      : 'Storage ready';
    const bookingCoverage = bookingCoverageForPlan(components, itinerarySavedReservations);
    const planningBurden = bookingPlan.planning_burden;
    const bookingHandoff = bookingPlan.booking_handoff;
    const bookingChecklist = bookingPlan.booking_checklist || itineraryPlanWithReservationCoverage?.trip_packet?.booking_checklist;
    const durationAlignment = bookingPlan.duration_alignment;
    const showDurationAlignment = durationAlignment?.status && durationAlignment.status !== 'aligned';

    return (
      <View
        style={styles.bookingPanel}
        onLayout={(event) => setBookingSectionOffsetY(event.nativeEvent.layout.y)}
      >
        <View style={styles.bookingHeader}>
          <Text style={styles.bookingTitle}>Booking & logistics</Text>
          <Text style={styles.bookingStatus}>{bookingReadinessLabel}</Text>
        </View>
        {bookingSummary?.message ? (
          <Text style={styles.bookingContextText}>{bookingSummary.message}</Text>
        ) : null}
        {showDurationAlignment ? (
          <View style={[
            styles.bookingDurationBox,
            durationAlignment.status === 'needs_attention' && styles.bookingDurationBoxNeedsAttention,
          ]}>
            <Text style={styles.bookingDurationKicker}>Trip duration check</Text>
            <Text style={styles.bookingDurationTitle}>
              {durationAlignment.headline || 'Review this trip length'}
            </Text>
            {durationAlignment.message ? (
              <Text style={styles.bookingDurationText}>{durationAlignment.message}</Text>
            ) : null}
            {durationAlignment.next_action ? (
              <Text style={styles.bookingDurationAction}>{durationAlignment.next_action}</Text>
            ) : null}
          </View>
        ) : null}
        {planningBurden ? (
          <View style={[
            styles.planningBurdenBox,
            planningBurden.level === 'low' && styles.planningBurdenBoxLow,
            planningBurden.level === 'high' && styles.planningBurdenBoxHigh,
          ]}>
            <View style={styles.planningBurdenHeader}>
              <View style={styles.planningBurdenTitleBlock}>
                <Text style={styles.planningBurdenKicker}>Planning burden</Text>
                <Text style={styles.planningBurdenTitle} numberOfLines={2}>
                  {planningBurden.headline || 'Adventour checked what still needs planning.'}
                </Text>
              </View>
              <Text style={[
                styles.planningBurdenPill,
                planningBurden.level === 'low' && styles.planningBurdenPillLow,
                planningBurden.level === 'high' && styles.planningBurdenPillHigh,
              ]}>
                {(planningBurden.level || 'check').toUpperCase()}
              </Text>
            </View>
            {planningBurden.next_action ? (
              <Text style={styles.planningBurdenAction} numberOfLines={2}>
                {planningBurden.next_action}
              </Text>
            ) : null}
            <View style={styles.planningBurdenChipRow}>
              <Text style={styles.planningBurdenChip}>{planningBurden.action_needed_count || 0} action</Text>
              <Text style={styles.planningBurdenChip}>{planningBurden.setup_count || 0} setup</Text>
              <Text style={styles.planningBurdenChip}>{planningBurden.manual_count || 0} manual</Text>
            </View>
          </View>
        ) : null}
        {bookingSummary?.missing_inputs?.length ? (
          <Text style={styles.bookingMissingText}>
            Add {bookingSummary.missing_inputs.join(', ').replace(/_/g, ' ')} to prepare booking steps.
          </Text>
        ) : null}
        {(bookingPlan.origin || bookingPlan.travel_dates?.start || bookingPlan.travel_dates?.end) ? (
          <Text style={styles.bookingContextText}>
            {bookingPlan.origin ? `From ${bookingPlan.origin}` : 'Origin not set'}
            {bookingPlan.travel_dates?.start || bookingPlan.travel_dates?.end
              ? ` - ${bookingPlan.travel_dates?.start || 'start?'} to ${bookingPlan.travel_dates?.end || 'end?'}`
            : ''}
          </Text>
        ) : null}
        {bookingChecklist?.items?.length ? (
          <View style={[
            styles.bookingChecklistBox,
            bookingChecklist.blocking_count ? styles.bookingChecklistBoxNeedsDetails : styles.bookingChecklistBoxReady,
          ]}>
            <View style={styles.bookingChecklistHeader}>
              <View style={styles.bookingChecklistTitleBlock}>
                <Text style={styles.bookingChecklistKicker}>Bookability checklist</Text>
                <Text style={styles.bookingChecklistTitle} numberOfLines={2}>
                  {bookingChecklist.headline || 'Adventour checked what is ready to book, save, and set up.'}
                </Text>
              </View>
              <Text style={[
                styles.bookingChecklistStatus,
                bookingChecklist.blocking_count ? styles.bookingChecklistStatusNeedsDetails : styles.bookingChecklistStatusReady,
              ]}>
                {bookingChecklist.blocking_count ? `${bookingChecklist.blocking_count} block` : 'Usable'}
              </Text>
            </View>
            <View style={styles.bookingChecklistChipRow}>
              {bookingChecklist.items.slice(0, 5).map((item) => (
                <View
                  key={`${item.id || item.label}-${item.status}`}
                  style={[
                    styles.bookingChecklistChip,
                    item.status === 'ready' && styles.bookingChecklistChipReady,
                    item.blocking && styles.bookingChecklistChipBlocking,
                  ]}
                >
                  <Text style={[
                    styles.bookingChecklistChipLabel,
                    item.blocking && styles.bookingChecklistChipLabelBlocking,
                  ]}>
                    {item.status === 'ready' ? 'Ready' : item.blocking ? 'Need' : 'Manual'}
                  </Text>
                  <Text style={styles.bookingChecklistChipText} numberOfLines={1}>
                    {item.label || item.id || 'Booking step'}
                  </Text>
                </View>
              ))}
            </View>
            {bookingChecklist.next_action ? (
              <Text style={styles.bookingChecklistAction} numberOfLines={2}>
                {bookingChecklist.next_action}
              </Text>
            ) : null}
          </View>
        ) : null}
        {bookingHandoff ? (
          <View style={[
            styles.bookingHandoffBox,
            bookingHandoff.status === 'ready' && styles.bookingHandoffBoxReady,
            bookingHandoff.status === 'needs_details' && styles.bookingHandoffBoxNeedsDetails,
          ]}>
            <View style={styles.bookingHandoffHeader}>
              <View style={styles.bookingHandoffTitleBlock}>
                <Text style={styles.bookingHandoffKicker}>Travel handoff</Text>
                <Text style={styles.bookingHandoffTitle} numberOfLines={2}>
                  {bookingHandoff.headline || 'Adventour organized the trip pieces you can book and save.'}
                </Text>
              </View>
              <Text style={[
                styles.bookingHandoffStatus,
                bookingHandoff.status === 'ready' && styles.bookingHandoffStatusReady,
                bookingHandoff.status === 'needs_details' && styles.bookingHandoffStatusNeedsDetails,
              ]}>
                {bookingHandoff.status === 'ready' ? 'Ready' : bookingHandoff.status === 'needs_details' ? 'Needs info' : 'Manual'}
              </Text>
            </View>
            <View style={styles.bookingHandoffMetricRow}>
              <Text style={styles.bookingHandoffMetric}>{bookingHandoff.ready_to_quote_count || 0} quote links</Text>
              <Text style={styles.bookingHandoffMetric}>{bookingHandoff.ready_to_save_count || 0} save slots</Text>
              <Text style={styles.bookingHandoffMetric}>{bookingHandoff.missing_input_count || 0} missing</Text>
            </View>
            {bookingHandoff.next_step ? (
              <Text style={styles.bookingHandoffNext} numberOfLines={2}>
                {bookingHandoff.next_step}
              </Text>
            ) : null}
            {bookingHandoff.required_inputs?.length ? (
              <View style={styles.bookingHandoffChipRow}>
                {bookingHandoff.required_inputs.slice(0, 4).map((input) => (
                  <Text key={`${input.id}-${input.component_type || 'trip'}`} style={styles.bookingHandoffNeedChip}>
                    {input.label}
                  </Text>
                ))}
              </View>
            ) : null}
            {bookingHandoff.quote_ready?.length ? (
              <View style={styles.bookingHandoffActionRow}>
                {bookingHandoff.quote_ready.slice(0, 2).map((link) => (
                  <TouchableOpacity
                    key={`${link.component_type}-${link.provider_label}-${link.url}`}
                    style={styles.bookingHandoffAction}
                    onPress={() => link.url && Linking.openURL(link.url)}
                    disabled={!link.url}
                    activeOpacity={0.84}
                  >
                    <Text style={styles.bookingHandoffActionLabel}>{link.label || link.component_type}</Text>
                    <Text style={styles.bookingHandoffActionProvider} numberOfLines={1}>
                      {link.provider_label || 'Open provider'}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
            {bookingHandoff.setup_ready?.length ? (
              <Text style={styles.bookingHandoffSetup} numberOfLines={2}>
                Local setup: {bookingHandoff.setup_ready[0].provider_label || bookingHandoff.setup_ready[0].label || 'Local travel'}
                {bookingHandoff.setup_ready[0].recommended_option?.label
                  ? ` via ${bookingHandoff.setup_ready[0].recommended_option?.label}`
                  : ''}
              </Text>
            ) : null}
            {bookingHandoff.save_ready?.length ? (
              <TouchableOpacity
                style={styles.bookingHandoffSaveButton}
                onPress={() => openReservationDraftFromBookingLink(bookingHandoff.save_ready![0])}
                activeOpacity={0.84}
              >
                <Text style={styles.bookingHandoffSaveText}>Save first confirmation</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
        {bookingPlan.next_best_actions?.length ? (
          <View style={styles.bookingNextActions}>
            <Text style={styles.bookingNextActionsTitle}>Next up</Text>
            {bookingPlan.next_best_actions.slice(0, 3).map((action) => (
              <Text key={`${action.type}-${action.label}`} style={styles.bookingNextActionText}>
                {action.label}: {action.detail}
              </Text>
            ))}
          </View>
        ) : null}
        {bookingPlan.booking_timeline?.items?.length ? (
          <View style={styles.bookingTimelineBox}>
            <View style={styles.bookingTimelineHeader}>
              <View>
                <Text style={styles.bookingTimelineKicker}>Booking sequence</Text>
                <Text style={styles.bookingTimelineTitle}>
                  {bookingPlan.booking_timeline.headline || 'Adventour ordered the booking steps for this route.'}
                </Text>
              </View>
              <Text style={[
                styles.bookingTimelineStatus,
                bookingPlan.booking_timeline.status === 'low_friction' && styles.bookingTimelineStatusReady,
              ]}>
                {bookingPlan.booking_timeline.status === 'low_friction' ? 'Ready' : 'Steps'}
              </Text>
            </View>
            {bookingPlan.booking_timeline.items.slice(0, 4).map((item, index) => (
              <View key={`${item.phase}-${item.label}-${index}`} style={styles.bookingTimelineItem}>
                <Text style={[
                  styles.bookingTimelineStep,
                  item.status === 'ready' && styles.bookingTimelineStepReady,
                  item.status === 'action_needed' && styles.bookingTimelineStepAction,
                ]}>
                  {index + 1}
                </Text>
                <View style={styles.bookingTimelineText}>
                  <View style={styles.bookingTimelineItemHeader}>
                    <Text style={styles.bookingTimelineLabel}>{item.label || item.phase}</Text>
                    {item.phase ? (
                      <Text style={styles.bookingTimelinePhase}>{item.phase}</Text>
                    ) : null}
                  </View>
                  <Text style={styles.bookingTimelineDetail} numberOfLines={2}>
                    {item.action || item.detail || 'Review this booking step before launch.'}
                  </Text>
                  {(item.provider || item.stores_reservation) ? (
                    <Text style={styles.bookingTimelineProvider} numberOfLines={1}>
                      {item.provider || 'Save confirmation in Adventour'}
                      {item.stores_reservation ? ' - save details' : ''}
                    </Text>
                  ) : null}
                </View>
                {item.source_url ? (
                  <TouchableOpacity onPress={() => Linking.openURL(item.source_url!)} activeOpacity={0.82}>
                    <Text style={styles.bookingTimelineOpen}>Open</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}
        {bookingPlan.booking_action_links?.length ? (
          <View style={styles.bookingQuickLinks}>
            <View style={styles.bookingQuickHeader}>
              <Text style={styles.bookingQuickTitle}>Quick booking links</Text>
              <Text style={styles.bookingQuickSubtitle}>Open, compare, then save confirmations.</Text>
            </View>
            <View style={styles.bookingQuickGrid}>
              {bookingPlan.booking_action_links.slice(0, 4).map((link) => (
                <View
                  key={`${link.component_type}-${link.provider_label}-${link.url}`}
                  style={styles.bookingQuickCard}
                >
                  <Text style={styles.bookingQuickLabel}>{link.label || link.component_type}</Text>
                  <Text style={styles.bookingQuickProvider} numberOfLines={1}>
                    {link.provider_label || 'Open provider'}
                  </Text>
                  {link.note ? (
                    <Text style={styles.bookingQuickNote} numberOfLines={2}>{link.note}</Text>
                  ) : null}
                  <View style={styles.bookingQuickActions}>
                    <TouchableOpacity
                      style={[styles.bookingQuickButton, !link.url && styles.bookingQuickButtonDisabled]}
                      onPress={() => link.url && Linking.openURL(link.url)}
                      disabled={!link.url}
                      activeOpacity={0.84}
                    >
                      <Text style={styles.bookingQuickButtonText}>{link.url ? 'Open' : 'No link'}</Text>
                    </TouchableOpacity>
                    {link.stores_reservation ? (
                      <TouchableOpacity
                        style={[styles.bookingQuickButton, styles.bookingQuickSaveButton]}
                        onPress={() => openReservationDraftFromBookingLink(link)}
                        activeOpacity={0.84}
                      >
                        <Text style={[styles.bookingQuickButtonText, styles.bookingQuickSaveText]}>Save</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              ))}
            </View>
          </View>
        ) : null}
        {bookingPlan.prep_checklist?.items?.length ? (
          <View style={styles.bookingPrepBox}>
            <View style={styles.bookingPrepHeader}>
              <Text style={styles.bookingPrepTitle}>Travel prep</Text>
              <Text style={[
                styles.bookingPrepStatus,
                bookingPlan.prep_checklist.status === 'needs_attention' && styles.bookingPrepStatusAttention,
              ]}>
                {bookingPlan.prep_checklist.status === 'needs_attention' ? 'Needs attention' : 'Ready'}
              </Text>
            </View>
            {bookingPlan.prep_checklist.headline ? (
              <Text style={styles.bookingPrepHeadline}>{bookingPlan.prep_checklist.headline}</Text>
            ) : null}
            {bookingPlan.prep_checklist.items.slice(0, 5).map((item) => (
              <View key={item.id} style={styles.bookingPrepItem}>
                <Text style={[
                  styles.bookingPrepItemPill,
                  item.status === 'ready' && styles.bookingPrepItemReady,
                  item.status === 'action_needed' && styles.bookingPrepItemAction,
                  item.status === 'manual' && styles.bookingPrepItemManual,
                ]}>
                  {item.status === 'action_needed' ? 'To do' : item.status === 'manual' ? 'Save' : item.status}
                </Text>
                <View style={styles.bookingPrepItemText}>
                  <Text style={styles.bookingPrepItemLabel}>{item.label}</Text>
                  {item.action || item.detail ? (
                    <Text style={styles.bookingPrepItemDetail} numberOfLines={2}>
                      {item.action || item.detail}
                    </Text>
                  ) : null}
                  {item.provider ? (
                    <Text style={styles.bookingPrepProvider} numberOfLines={1}>
                      {item.provider}{item.estimate ? ` - ${item.estimate.currency} $${item.estimate.per_person_low}-${item.estimate.per_person_high} / person` : ''}
                    </Text>
                  ) : null}
                </View>
                {item.source_url ? (
                  <TouchableOpacity onPress={() => Linking.openURL(item.source_url!)} activeOpacity={0.82}>
                    <Text style={styles.bookingPrepOpen}>Open</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ))}
          </View>
        ) : null}
        {components.map((component) => {
          const estimate = component.estimate;
          const showPlanningSteps = component.type !== 'local_transport' && Boolean(component.next_steps?.length);
          const showProviderOptions = component.type !== 'local_transport' && Boolean(component.provider_options?.length);
          return (
            <View key={component.id} style={styles.bookingItem}>
              <View style={styles.bookingItemHeader}>
                <Text style={styles.bookingLabel}>{component.label}</Text>
                <Text style={[
                  styles.bookingPill,
                  component.status === 'estimated' && styles.bookingPillReady,
                  component.status === 'ready_for_provider' && styles.bookingPillReady,
                  (component.status === 'optional_for_day_trip' || component.status === 'not_needed_for_day_trip') && styles.bookingPillOptional,
                ]}>
                  {bookingStatusLabel(component.status)}
                </Text>
              </View>
              {estimate ? (
                <Text style={styles.bookingEstimate}>
                  {estimate.currency} ${estimate.per_person_low}-${estimate.per_person_high} / person
                </Text>
              ) : null}
              {component.action ? (
                <Text style={styles.bookingAction}>{component.action}</Text>
              ) : null}
              {component.search_hint ? (
                <Text style={styles.bookingSearchHint}>Search: {component.search_hint}</Text>
              ) : null}
              {component.missing_inputs?.length ? (
                <Text style={styles.bookingComponentMissing}>
                  Needs {component.missing_inputs.join(', ').replace(/_/g, ' ')}
                </Text>
              ) : null}
              {showPlanningSteps ? (
                <View style={styles.bookingStepBox}>
                  <Text style={styles.bookingStepTitle}>Booking steps</Text>
                  {component.next_steps?.slice(0, 4).map((step) => (
                    <Text key={step} style={styles.bookingStepText}>- {step}</Text>
                  ))}
                </View>
              ) : null}
              {showProviderOptions ? (
                <View style={styles.bookingProviderRow}>
                  {component.provider_options?.map((option) => (
                    <TouchableOpacity
                      key={option.label}
                      style={styles.bookingProviderPill}
                      onPress={() => option.url && Linking.openURL(option.url)}
                      disabled={!option.url}
                      activeOpacity={0.82}
                    >
                      <Text style={styles.bookingProviderText}>{option.label}</Text>
                      {option.note ? (
                        <Text style={styles.bookingProviderNote} numberOfLines={2}>{option.note}</Text>
                      ) : null}
                    </TouchableOpacity>
                  ))}
                </View>
              ) : null}
              {component.type === 'local_transport' && (component.setup_provider || component.setup_steps?.length) ? (
                <View style={styles.transportSetupBox}>
                  <View style={styles.transportSetupHeader}>
                    <Text style={styles.transportSetupTitle}>
                      {component.setup_provider ? `${component.setup_provider} setup` : 'Local travel setup'}
                    </Text>
                    {component.setup_source_url ? (
                      <TouchableOpacity onPress={() => Linking.openURL(component.setup_source_url!)} activeOpacity={0.82}>
                        <Text style={styles.transportSetupLink}>Open</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                  {component.setup_steps?.slice(0, 3).map((step) => (
                    <Text key={step} style={styles.transportSetupStep}>- {step}</Text>
                  ))}
                </View>
              ) : null}
              {component.type === 'local_transport' && component.options?.length ? (
                <View style={styles.transportOptions}>
                  <Text style={styles.transportDistance}>{formatRouteDistance(component.route_distance_meters)}</Text>
                  {component.options.map((option) => (
                    <View key={option.id} style={[styles.transportOption, option.recommended && styles.transportOptionRecommended]}>
                      <View style={styles.transportOptionHeader}>
                        <Text style={[styles.transportOptionLabel, option.recommended && styles.transportOptionLabelRecommended]}>
                          {option.label}
                        </Text>
                        <Text style={[styles.transportOptionEstimate, option.recommended && styles.transportOptionEstimateRecommended]}>
                          {option.estimate.currency} ${option.estimate.per_person_low}-${option.estimate.per_person_high}
                        </Text>
                      </View>
                      <Text style={[styles.transportOptionWhy, option.recommended && styles.transportOptionWhyRecommended]}>
                        {option.recommended ? 'Best fit: ' : ''}{option.why}
                      </Text>
                      {option.setup ? (
                        <Text style={[styles.transportOptionSetup, option.recommended && styles.transportOptionSetupRecommended]}>
                          {option.setup}
                        </Text>
                      ) : null}
                    </View>
                  ))}
                </View>
              ) : null}
              {component.stores_reservation ? (
                <TouchableOpacity
                  style={styles.bookingAddButton}
                  onPress={() => openReservationDraft(component)}
                  activeOpacity={0.82}
                >
                  <Text style={styles.bookingAddButtonText}>Add booking details</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          );
        })}
        {reservationDraft ? (
          <View style={styles.reservationForm}>
            <View style={styles.reservationFormHeader}>
              <Text style={styles.reservationFormTitle}>
                {reservationDraft.id ? 'Edit booking detail' : 'Save booking detail'}
              </Text>
              <TouchableOpacity onPress={() => setReservationDraft(null)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Text style={styles.reservationCancel}>Cancel</Text>
              </TouchableOpacity>
            </View>
            <TextInput
              style={styles.reservationInput}
              value={reservationDraft.title}
              onChangeText={(value) => setReservationDraft((current) => current ? { ...current, title: value } : current)}
              placeholder="Title"
            />
            <View style={styles.reservationInputRow}>
              <TextInput
                style={[styles.reservationInput, styles.reservationInputHalf]}
                value={reservationDraft.provider}
                onChangeText={(value) => setReservationDraft((current) => current ? { ...current, provider: value } : current)}
                placeholder="Provider"
              />
              <TextInput
                style={[styles.reservationInput, styles.reservationInputHalf]}
                value={reservationDraft.confirmation_code}
                onChangeText={(value) => setReservationDraft((current) => current ? { ...current, confirmation_code: value } : current)}
                placeholder="Confirmation"
                autoCapitalize="characters"
              />
            </View>
            <View style={styles.reservationInputRow}>
              <TextInput
                style={[styles.reservationInput, styles.reservationInputHalf]}
                value={reservationDraft.cost_total}
                onChangeText={(value) => setReservationDraft((current) => current ? { ...current, cost_total: value } : current)}
                placeholder="Cost total"
                keyboardType="decimal-pad"
              />
              <TextInput
                style={[styles.reservationInput, styles.reservationInputHalf]}
                value={reservationDraft.booking_url}
                onChangeText={(value) => setReservationDraft((current) => current ? { ...current, booking_url: value } : current)}
                placeholder="Booking link"
                autoCapitalize="none"
              />
            </View>
            <TextInput
              style={[styles.reservationInput, styles.reservationNotesInput]}
              value={reservationDraft.notes}
              onChangeText={(value) => setReservationDraft((current) => current ? { ...current, notes: value } : current)}
              placeholder="Notes"
              multiline
            />
            <TouchableOpacity
              style={[styles.reservationSaveButton, reservationSaving && styles.planButtonDisabled]}
              onPress={saveReservationDraft}
              disabled={reservationSaving}
              activeOpacity={0.86}
            >
              <Text style={styles.reservationSaveText}>
                {reservationSaving ? 'Saving...' : reservationDraft.id ? 'Update details' : 'Save details'}
              </Text>
            </TouchableOpacity>
          </View>
        ) : null}
        {bookingCoverage.items.length ? (
          <View style={styles.bookingCoverage}>
            <View style={styles.bookingCoverageHeader}>
              <View>
                <Text style={styles.bookingCoverageTitle}>Booking wallet</Text>
                <Text style={styles.bookingCoverageText}>
                  {bookingCoverage.savedCount}/{bookingCoverage.items.length} trip pieces saved
                  {bookingCoverage.confirmedCount ? ` - ${bookingCoverage.confirmedCount} with confirmation/link` : ''}
                </Text>
              </View>
              <Text style={[
                styles.bookingCoverageStatus,
                bookingCoverage.savedCount === bookingCoverage.items.length && styles.bookingCoverageStatusReady,
              ]}>
                {bookingCoverage.savedCount === bookingCoverage.items.length ? 'Covered' : 'Missing'}
              </Text>
            </View>
            <View style={styles.bookingCoverageChipRow}>
              {bookingCoverage.items.map((item) => (
                <Text
                  key={item.id}
                  onPress={item.status === 'missing' ? () => openReservationDraft(item.component) : undefined}
                  style={[
                    styles.bookingCoverageChip,
                    item.status === 'saved' && styles.bookingCoverageChipSaved,
                  ]}
                >
                  {item.status === 'saved' ? 'Saved' : 'Missing'} {item.label}
                </Text>
              ))}
            </View>
            {bookingCoverage.missingLabels.length ? (
              <Text style={styles.bookingCoverageHint}>
                Tap a missing piece to prefill details for {bookingCoverage.missingLabels.slice(0, 3).join(', ')} before starting.
              </Text>
            ) : null}
          </View>
        ) : null}
        {itinerarySavedReservations.length ? (
          <View style={styles.savedReservations}>
            <Text style={styles.savedReservationsTitle}>Saved booking details</Text>
            <Text style={styles.savedReservationsSummary}>
              This plan has {itinerarySavedReservations.length} saved detail{itinerarySavedReservations.length === 1 ? '' : 's'}
              {savedReservationCostTotal > 0 ? ` worth ${currency} $${savedReservationCostTotal.toFixed(2)}` : ''}
              {Object.keys(savedReservationTypeCounts).length ? ` (${Object.keys(savedReservationTypeCounts).join(', ')})` : ''}.
            </Text>
            {itinerarySavedReservations.slice(0, 4).map((reservation) => (
              <View key={reservation.id} style={styles.savedReservationItem}>
                <View style={styles.savedReservationText}>
                  <Text style={styles.savedReservationTitle}>{reservation.title}</Text>
                  <Text style={styles.savedReservationMeta} numberOfLines={1}>
                    {reservation.provider || reservation.reservation_type}
                    {reservation.confirmation_code ? ` - ${reservation.confirmation_code}` : ''}
                    {reservation.cost_total ? ` - ${reservation.currency || 'USD'} $${reservation.cost_total}` : ''}
                    {!reservation.adventour_session_id && pendingItineraryReservationIds.includes(reservation.id) ? ' - attaches when started' : ''}
                  </Text>
                </View>
                <View style={styles.savedReservationActions}>
                  <TouchableOpacity onPress={() => openExistingReservationDraft(reservation)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Text style={styles.savedReservationEdit}>Edit</Text>
                  </TouchableOpacity>
                  <TouchableOpacity onPress={() => deleteReservation(reservation.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                    <Text style={styles.savedReservationRemove}>Remove</Text>
                  </TouchableOpacity>
                </View>
              </View>
            ))}
          </View>
        ) : null}
        {bookingPlan.reservation_storage?.message ? (
          <Text style={styles.bookingStorageNote}>{bookingPlan.reservation_storage.message}</Text>
        ) : null}
      </View>
    );
  };

  const renderTripCalendar = () => {
    if (!calendarPicker) {
      return null;
    }

    const todayValue = formatTripDateValue(new Date());
    const selectedValue = calendarPicker === 'start' ? tripStartDate : tripEndDate;
    const calendarDays = calendarDaysForMonth(calendarMonth);
    const weekdays = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

    return (
      <View style={styles.tripCalendarPanel}>
        <View style={styles.tripCalendarHeader}>
          <TouchableOpacity
            style={styles.tripCalendarNavButton}
            onPress={() => setCalendarMonth((current) => addMonths(current, -1))}
            activeOpacity={0.82}
          >
            <Text style={styles.tripCalendarNavText}>‹</Text>
          </TouchableOpacity>
          <View style={styles.tripCalendarTitleBlock}>
            <Text style={styles.tripCalendarKicker}>
              Pick {calendarPicker === 'start' ? 'start' : 'end'} date
            </Text>
            <Text style={styles.tripCalendarTitle}>{calendarMonthLabel(calendarMonth)}</Text>
          </View>
          <TouchableOpacity
            style={styles.tripCalendarNavButton}
            onPress={() => setCalendarMonth((current) => addMonths(current, 1))}
            activeOpacity={0.82}
          >
            <Text style={styles.tripCalendarNavText}>›</Text>
          </TouchableOpacity>
        </View>
        <View style={styles.tripCalendarWeekRow}>
          {weekdays.map((weekday, index) => (
            <Text key={`${weekday}-${index}`} style={styles.tripCalendarWeekday}>{weekday}</Text>
          ))}
        </View>
        <View style={styles.tripCalendarGrid}>
          {calendarDays.map((date, index) => {
            if (!date) {
              return <View key={`blank-${index}`} style={styles.tripCalendarDayBlank} />;
            }

            const value = formatTripDateValue(date);
            const selected = value === selectedValue;
            const today = value === todayValue;

            return (
              <TouchableOpacity
                key={value}
                style={[
                  styles.tripCalendarDay,
                  today && styles.tripCalendarDayToday,
                  selected && styles.tripCalendarDaySelected,
                ]}
                onPress={() => {
                  if (calendarPicker === 'start') {
                    setTripStartDate(value);
                    if (tripEndDate && parseTripDateValue(tripEndDate) !== null && parseTripDateValue(value)! > parseTripDateValue(tripEndDate)!) {
                      setTripEndDate('');
                    }
                    setCalendarPicker('end');
                  } else {
                    setTripEndDate(value);
                    setCalendarPicker(null);
                  }
                  setItineraryPlan(null);
                }}
                activeOpacity={0.82}
              >
                <Text style={[
                  styles.tripCalendarDayText,
                  selected && styles.tripCalendarDayTextSelected,
                ]}>
                  {date.getDate()}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>
      </View>
    );
  };

  const renderItineraryPlan = () => {
    const price = itineraryPlan?.price_breakdown?.per_person;
    const currency = itineraryPlan?.price_breakdown?.currency || 'USD';
    const combinedKnownLow = price ? price.total_known_low + savedReservationEstimateAddOnPerPerson : 0;
    const combinedKnownHigh = price ? price.total_known_high + savedReservationEstimateAddOnPerPerson : 0;
    const itineraryScoutStyle = itineraryPlan?.learned_rerank?.applied
      ? (LEARNED_SCORING_PROFILE || scoringProfile)
      : scoutStyleForId(itineraryPlan?.scoring_profile) || scoringProfile;
    const itineraryScoutLabel = itineraryScoutStyle.id === 'auto_scout'
      ? itineraryScoutStyle.label
      : `${itineraryScoutStyle.label} scout`;
    const routeDiagnostic = itineraryDiagnosticFromFilterSummary(itineraryPlan);
    const eventSourceSummary = localEventSourceSummary(itineraryPlan);
    const eventSocialSummary = localEventSocialSummary(itineraryPlan);
    const launchChecklist = itineraryPlan ? (itineraryPlan.launch_checklist || launchChecklistForItineraryPlan(itineraryPlan)) : null;
    const itineraryStory = itineraryPlan ? (itineraryPlan.itinerary_story || itineraryStoryForItineraryPlan(itineraryPlan)) : null;
    const itineraryScenarioReadiness = itineraryPlan?.scenario_readiness;
    const itineraryFriendReadiness = itineraryScenarioReadiness?.friend_readiness || null;
    const itineraryTestVerdict = itineraryScenarioReadiness?.test_verdict;
    const itineraryTopRemediation = itineraryScenarioReadiness?.remediation_plan?.[0];
    const itineraryTopRemediationAction = itineraryTopRemediation?.actions?.[0];
    const itineraryTopRemediationAdjustment = remediationAdjustmentLabel(itineraryTopRemediation?.adjustment);
    const visibleTestVerdictDimensions = prioritizedTestVerdictDimensions(itineraryTestVerdict?.dimensions);
    const itineraryPipelineDiagnostic = itineraryPlan?.recommendation_quality?.diagnostic;
    const itineraryPipelineStages = (itineraryPipelineDiagnostic?.stages || [])
      .filter((stage) => stage.status !== 'pass')
      .slice(0, selectedFriendIds.length > 0 ? 5 : 4);
    const visibleItineraryPipelineStages = itineraryPipelineStages.length
      ? itineraryPipelineStages
      : (itineraryPipelineDiagnostic?.stages || []).slice(0, 4);
    const itineraryPipelineAction = itineraryPipelineDiagnostic?.primary_issue?.next_action
      || itineraryPipelineDiagnostic?.next_actions?.[0];
    const routeAuthenticity = itineraryPlan?.route_authenticity || itineraryPlan?.route_readiness?.authenticity_summary;
    const itineraryScenarioStatus = itineraryScenarioReadiness?.status === 'ready'
      ? 'Friend ready'
      : itineraryScenarioReadiness?.status === 'needs_attention'
        ? 'Tune'
        : 'Watch';
    const itineraryFriendStatusLabel = itineraryFriendReadiness?.status === 'ready'
      ? 'Friend ready'
      : itineraryFriendReadiness?.status === 'needs_attention'
        ? 'Needs match'
        : 'Review';
    const itineraryFriendAction = itineraryFriendReadiness?.next_actions?.[0] || itineraryFriendReadiness?.watchouts?.[0];
    const itineraryFriendSwap = itineraryFriendReadiness?.suggested_swaps?.[0]
      || itineraryFriendReadiness?.underserved_members?.flatMap((member) => member.suggested_swaps || [])?.[0];
    const itineraryFriendSuggestionTags = Array.from(new Set(
      (itineraryFriendReadiness?.underserved_members || [])
        .flatMap((member) => member.suggested_query_tags || [])
        .filter(Boolean)
    )).slice(0, 4);
    const itineraryBoostLabels = Array.from(new Set(
      (itineraryPlan?.retrieval_context?.boost_query_tags || [])
        .map((tag) => tagGroupDisplayLabel(tag) || tag.replace(/_/g, ' '))
    )).slice(0, 3);
    const canStartPlan = itineraryPlan ? launchChecklist?.can_start !== false : false;
    const itineraryPlanWithReservationCoverage = itineraryPlan
      ? withReservationCoverage(itineraryPlan, itinerarySavedReservations)
      : null;
    const tripPacket = itineraryPlanWithReservationCoverage?.trip_packet;
    const itinerarySwapGuide = itineraryPlanWithReservationCoverage
      ? (itineraryPlanWithReservationCoverage.swap_guide
        || tripPacket?.swap_guide
        || swapGuideForItineraryPlan(itineraryPlanWithReservationCoverage))
      : null;
    const routeModelConfidence = itineraryPlanWithReservationCoverage
      ? (itineraryPlanWithReservationCoverage.route_model_confidence
        || tripPacket?.route_model_confidence
        || routeModelConfidenceForItineraryPlan(itineraryPlanWithReservationCoverage))
      : null;
    const routeModelAction = routeModelConfidence?.warnings?.[0]
      || routeModelConfidence?.next_actions?.[0]
      || routeModelConfidence?.basis?.[0];
    const tripStyleFit = itineraryPlan?.trip_style_fit || tripPacket?.trip_style_fit;
    const tripStyleRouteDays = tripStyleFit?.route_days || itineraryPlan?.days.length || itineraryDayCount;
    const tripStyleFitTone = tripStyleFit?.status === 'ready'
      ? 'ready'
      : tripStyleFit?.status === 'needs_attention'
        ? 'attention'
        : 'watch';

    return (
      <View style={styles.planCard}>
        <View style={styles.planHeader}>
          <View style={styles.planHeaderText}>
            <Text style={styles.planKicker}>Planned Adventour</Text>
            <Text style={styles.planTitle}>
              {itineraryPlan?.title || 'Let Adventour shape the trip'}
            </Text>
            <Text style={styles.planSubtitle}>
              {itineraryPlan
                ? `${partyLabel} - ${itineraryPlan.days.length} day${itineraryPlan.days.length === 1 ? '' : 's'}${itineraryPlan.nights ? `, ${itineraryPlan.nights} night${itineraryPlan.nights === 1 ? '' : 's'}` : ''}`
                : `Choose the size of the adventure. Adventour will scout local-first stops, events, swaps, and travel handoff details.`}
            </Text>
            <View style={styles.planScoutPill}>
              <Text style={styles.planScoutLabel}>{itineraryScoutLabel}</Text>
              <Text style={styles.planScoutHelper}>{itineraryScoutStyle.helper}</Text>
            </View>
          </View>
          <TouchableOpacity
            style={[styles.planButton, !fullItineraryReady && styles.planButtonDisabled]}
            onPress={() => loadItineraryPlan()}
            disabled={!fullItineraryReady}
            activeOpacity={0.86}
          >
            {itineraryLoading ? (
              <ActivityIndicator color="#fffdf8" size="small" />
            ) : (
              <Text style={styles.planButtonText}>
                {!hasTripDateRange ? 'Pick dates' : itineraryPlan ? 'Remix' : 'Launch plan'}
              </Text>
            )}
          </TouchableOpacity>
        </View>

        <View style={styles.magicSetupPanel}>
          <View style={styles.magicSetupHeader}>
            <View style={styles.magicSetupTextBlock}>
              <Text style={styles.magicSetupKicker}>Trip setup</Text>
              <Text style={styles.magicSetupTitle}>
                {inferredPlanOption.label} - {tripSetupSummary}
              </Text>
              <Text style={styles.magicSetupHint}>
                Dates and preferences help flights, stays, events, and booking prep. You can skip them and still launch.
              </Text>
            </View>
            <TouchableOpacity
              style={styles.magicSetupButton}
              onPress={() => setTripSetupOpen((open) => !open)}
              activeOpacity={0.84}
            >
              <Text style={styles.magicSetupButtonText}>{tripSetupOpen ? 'Done' : 'Add details'}</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            style={styles.magicFineTuneButton}
            onPress={() => setRouteControlsOpen((open) => !open)}
            activeOpacity={0.84}
          >
            <Text style={styles.magicFineTuneText}>
              {routeControlsOpen ? 'Hide fine-tuning' : 'Fine-tune route scout'}
            </Text>
          </TouchableOpacity>
        </View>
        {tripStyleFit ? (
          <View style={[
            styles.tripStyleFitBox,
            tripStyleFitTone === 'ready' && styles.tripStyleFitBoxReady,
            tripStyleFitTone === 'attention' && styles.tripStyleFitBoxAttention,
          ]}>
            <View style={styles.tripStyleFitHeader}>
              <View style={styles.tripStyleFitTitleBlock}>
                <Text style={styles.tripStyleFitKicker}>Trip style fit</Text>
                <Text style={styles.tripStyleFitTitle} numberOfLines={2}>
                  {tripStyleFit.headline || 'Adventour checked whether this trip style fits the route.'}
                </Text>
              </View>
              {typeof tripStyleFit.score === 'number' ? (
                <Text style={[
                  styles.tripStyleFitScore,
                  tripStyleFitTone === 'ready' && styles.tripStyleFitScoreReady,
                  tripStyleFitTone === 'attention' && styles.tripStyleFitScoreAttention,
                ]}>
                  {Math.round(tripStyleFit.score * 100)}%
                </Text>
              ) : null}
            </View>
            <View style={styles.tripStyleFitMetricRow}>
              <Text style={styles.tripStyleFitMetric}>
                {tripStyleRouteDays} day{tripStyleRouteDays === 1 ? '' : 's'}
              </Text>
              <Text style={styles.tripStyleFitMetric}>
                {tripStyleFit.nights || 0} night{(tripStyleFit.nights || 0) === 1 ? '' : 's'}
              </Text>
              {typeof tripStyleFit.quote_coverage === 'number' ? (
                <Text style={[
                  styles.tripStyleFitMetric,
                  tripStyleFit.quote_coverage >= 1 ? styles.tripStyleFitMetricReady : styles.tripStyleFitMetricCaution,
                ]}>
                  Quotes {Math.round(tripStyleFit.quote_coverage * 100)}%
                </Text>
              ) : null}
              {typeof tripStyleFit.event_route_match_count === 'number' && tripStyleFit.event_route_match_count > 0 ? (
                <Text style={[styles.tripStyleFitMetric, styles.tripStyleFitMetricReady]}>
                  {tripStyleFit.event_route_match_count} event{tripStyleFit.event_route_match_count === 1 ? '' : 's'}
                </Text>
              ) : null}
            </View>
            {(tripStyleFit.next_action || tripStyleFit.message) ? (
              <Text style={[
                styles.tripStyleFitText,
                tripStyleFitTone === 'attention' && styles.tripStyleFitTextCaution,
              ]} numberOfLines={2}>
                {tripStyleFit.next_action || tripStyleFit.message}
              </Text>
            ) : null}
          </View>
        ) : null}

        {routeControlsOpen ? (
          <>
        <View style={styles.comparePanel}>
          <View style={styles.compareHeader}>
            <View style={styles.compareHeaderText}>
              <Text style={styles.compareTitle}>Scout style check</Text>
              <Text style={styles.compareSubtitle}>Compare route readiness before rebuilding.</Text>
              {itineraryProviderUsageLabel ? (
                <Text style={styles.providerUsageInline}>
                  Live scout: {itineraryProviderUsageLabel}
                </Text>
              ) : null}
            </View>
            <TouchableOpacity
              style={[styles.compareButton, (!hasLaunchPoint || comparisonLoading) && styles.planButtonDisabled]}
              onPress={compareItineraryProfiles}
              disabled={!hasLaunchPoint || comparisonLoading}
              activeOpacity={0.86}
            >
              {comparisonLoading ? (
                <ActivityIndicator color="#123c69" size="small" />
              ) : (
                <Text style={styles.compareButtonText}>Compare</Text>
              )}
            </TouchableOpacity>
          </View>
          {itineraryComparisons.length ? (
            <View style={styles.comparisonList}>
              {itineraryComparisons.slice(0, 3).map((comparison) => {
                const style = scoutStyleForId(comparison.scoring_profile) || SCORING_PROFILE_OPTIONS[0];
                const readiness = comparison.route_readiness;
                const scenarioReadiness = comparison.scenario_readiness;
                const launchChecklist = comparison.launch_checklist;
                const explanation = comparison.comparison_explanation;
                const groupFit = comparison.group_fit_summary;
                const friendReadiness = scenarioReadiness?.friend_readiness;
                const friendTestPacket = comparison.friend_test_packet || comparison.plan?.trip_packet?.friend_test_packet;
                const rank = comparison.comparison_rank || {};
                const checklistIssueCount = (launchChecklist?.blocking_count || 0) + (launchChecklist?.action_count || 0);
                const compromiseBrief = comparison.group_compromise_brief || groupFit?.compromise_brief || friendTestPacket?.compromise_brief;
                const underservedNames = (friendReadiness?.underserved_members || groupFit?.underserved_members)
                  ?.slice(0, 2)
                  .map((member) => member.display_name)
                  .join(', ');
                const friendTestStatus = rank.friend_test_status || friendTestPacket?.friend_readiness_status || friendTestPacket?.status;
                const friendTestable = Boolean(rank.friend_testable || friendTestPacket?.friend_testable);
                const friendTestBlockerCount = rank.friend_test_blocker_count ?? (friendTestPacket?.blockers?.length || 0);
                const hasFriendRouteFit = Boolean(
                  (friendReadiness?.member_count && friendReadiness.member_count > 1)
                  || (friendTestPacket?.member_count && friendTestPacket.member_count > 1)
                );
                const hasGroupRouteFit = Boolean(groupFit?.member_count && groupFit.member_count > 1);
                const routePartyMessage = friendTestPacket?.headline
                  ? friendTestPacket.headline
                  : friendReadiness?.underserved_count
                  ? (compromiseBrief?.headline || `${underservedNames || 'Someone'} needs a stronger route stop.`)
                  : friendReadiness?.headline
                    ? friendReadiness.headline
                    : groupFit?.underserved_count
                      ? (compromiseBrief?.headline || `${underservedNames || 'Someone'} may need a better match.`)
                      : (compromiseBrief?.headline || groupFit?.message || `Balanced for ${groupFit?.member_count || friendReadiness?.member_count} travelers.`);
                const routePartyCaution = Boolean(
                  friendReadiness?.underserved_count
                  || (friendTestPacket && !friendTestable && (friendTestBlockerCount > 0 || (friendTestPacket.underserved_count || 0) > 0))
                  || groupFit?.underserved_count
                  || ['needs_coverage', 'uneven'].includes(String(compromiseBrief?.status || ''))
                );
                const isRecommended = comparison.scoring_profile === recommendedComparisonProfile;
                const isLoadedPlan = Boolean(
                  itineraryPlan
                  && comparison.plan?.request_id
                  && itineraryPlan.request_id === comparison.plan.request_id
                );
                const canUseComparison = Boolean(comparison.plan) && !isLoadedPlan;
                const scenarioLabel = scenarioReadiness?.status === 'ready'
                  ? 'Friend-ready'
                  : scenarioReadiness?.status === 'needs_attention'
                    ? 'Needs tuning'
                    : 'Watch';
                const comparisonSignals = [
                  typeof rank.trip_readiness_score === 'number'
                    ? {
                      key: 'trip',
                      label: 'Trip ready',
                      value: `${Math.round(rank.trip_readiness_score * 100)}%`,
                      tone: rank.trip_readiness_score >= 0.72 ? 'positive' : rank.trip_readiness_score < 0.52 ? 'caution' : 'neutral',
                    }
                    : null,
                  typeof rank.route_model_confidence_score === 'number' && rank.route_model_confidence_score > 0
                    ? {
                      key: 'model-signal',
                      label: 'Model',
                      value: `${Math.round(rank.route_model_confidence_score * 100)}%`,
                      tone: rank.route_model_confidence_score >= 0.72
                        ? 'positive'
                        : rank.route_model_confidence_score < 0.46 || (rank.route_model_warning_count || 0) > 0
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  rank.pipeline_issue_name
                    ? {
                      key: 'pipeline',
                      label: 'Pipeline',
                      value: rank.pipeline_issue_status === 'fail' || rank.pipeline_issue_status === 'needs_attention'
                        ? 'fix'
                        : 'tune',
                      tone: (rank.pipeline_issue_severity || 0) > 0 ? 'caution' : 'neutral',
                    }
                    : null,
                  typeof rank.logistics_readiness_score === 'number' && rank.logistics_readiness_score > 0
                    ? {
                      key: 'trip-logistics',
                      label: 'Logistics',
                      value: `${Math.round(rank.logistics_readiness_score * 100)}%`,
                      tone: rank.logistics_readiness_score >= 0.78 && !(rank.logistics_missing_input_count || 0)
                        ? 'positive'
                        : rank.logistics_readiness_score < 0.52 || (rank.logistics_missing_input_count || 0) > 0 || (rank.logistics_blocking_count || 0) > 0
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  typeof rank.booking_handoff_score === 'number' && rank.booking_handoff_score > 0
                    ? {
                      key: 'trip-handoff',
                      label: 'Trip handoff',
                      value: (rank.booking_command_open_link_count || rank.booking_command_save_prompt_count)
                        ? `${rank.booking_command_open_link_count || 0} open / ${rank.booking_command_save_prompt_count || 0} save`
                        : `${Math.round(rank.booking_handoff_score * 100)}%`,
                      tone: rank.booking_handoff_score >= 0.72 && !(rank.booking_command_action_count || 0)
                        ? 'positive'
                        : rank.booking_handoff_score < 0.45 || (rank.booking_command_action_count || 0) > 0
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  typeof rank.trip_style_fit_score === 'number' && rank.trip_style_fit_score > 0
                    ? {
                      key: 'trip-style-fit',
                      label: 'Style',
                      value: `${Math.round(rank.trip_style_fit_score * 100)}%`,
                      tone: rank.trip_style_fit_score >= 0.78
                        ? 'positive'
                        : rank.trip_style_fit_score < 0.55 || rank.trip_style_fit_status === 'needs_attention'
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  (rank.travel_quote_required_count || 0) > 0
                    ? {
                      key: 'travel-quotes',
                      label: 'Quotes',
                      value: `${rank.travel_quote_ready_count || 0}/${rank.travel_quote_required_count || 0}`,
                      tone: (rank.travel_quote_readiness_score || 0) >= 0.85
                        ? 'positive'
                        : (rank.travel_quote_missing_input_count || 0) > 0
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  rank.friend_member_count && rank.friend_member_count > 1 && typeof rank.friend_coverage_share === 'number'
                    ? {
                      key: 'friends',
                      label: 'Friends',
                      value: `${Math.round(rank.friend_coverage_share * 100)}%`,
                      tone: (rank.friend_coverage_share >= 1 && !(rank.friend_underserved_count || 0)) ? 'positive' : 'caution',
                    }
                    : null,
                  friendTestPacket || rank.friend_test_status || typeof rank.friend_test_score === 'number'
                    ? {
                      key: 'friend-test',
                      label: 'Friend test',
                      value: friendTestable
                        ? 'Ready'
                        : String(friendTestStatus || 'Watch').replace(/_/g, ' '),
                      tone: friendTestable ? 'positive' : friendTestBlockerCount > 0 ? 'caution' : 'neutral',
                    }
                    : null,
                  rank.friend_member_count && rank.friend_member_count > 1 && typeof rank.friend_average_fit === 'number'
                    ? {
                      key: 'route-fit',
                      label: 'Route fit',
                      value: `${Math.round(rank.friend_average_fit * 100)}%`,
                      tone: rank.friend_average_fit >= 0.7 ? 'positive' : 'neutral',
                    }
                    : null,
                  rank.friend_member_count && rank.friend_member_count > 1 && (rank.friend_rescue_count || 0) > 0
                    ? {
                      key: 'friend-rescue',
                      label: 'Made room',
                      value: rank.friend_rescued_members?.slice(0, 2).join(', ') || `${rank.friend_rescue_count} stop${rank.friend_rescue_count === 1 ? '' : 's'}`,
                      tone: 'positive',
                    }
                    : null,
                  rank.friend_member_count && rank.friend_member_count > 1 && (rank.swap_party_actionable_member_count || 0) > 0
                    ? {
                      key: 'group-swaps',
                      label: 'Group swaps',
                      value: `${rank.swap_party_actionable_member_count} ready`,
                      tone: 'positive',
                    }
                    : null,
                  typeof rank.authenticity_score === 'number' && rank.authenticity_score > 0
                    ? {
                      key: 'local',
                      label: 'Local',
                      value: `${Math.round(rank.authenticity_score * 100)}%`,
                      tone: rank.authenticity_score >= 0.7 ? 'positive' : rank.chain_risk && rank.chain_risk >= 0.35 ? 'caution' : 'neutral',
                    }
                    : null,
                  typeof rank.event_actionability_score === 'number' && rank.event_actionability_score > 0 && ((rank.event_route_match_count || 0) > 0 || (rank.event_actionable_count || 0) > 0)
                    ? {
                      key: 'event-plan',
                      label: 'Event plan',
                      value: (rank.event_reservation_ready_count || 0) > 0
                        ? `${rank.event_reservation_ready_count} RSVP`
                        : `${rank.event_actionable_count || 0} linked`,
                      tone: (rank.event_reservation_ready_count || 0) > 0 || rank.event_actionability_score >= 0.72
                        ? 'positive'
                        : 'neutral',
                    }
                    : null,
                  typeof rank.event_social_score === 'number' && (rank.event_social_score > 0 || (rank.event_social_anchor_count || 0) > 0)
                    ? {
                      key: 'social-events',
                      label: 'Social',
                      value: rank.event_friend_signal_count
                        ? `${rank.event_friend_signal_count} friend${rank.event_friend_signal_count === 1 ? '' : 's'}`
                        : `${Math.round(rank.event_social_score * 100)}%`,
                      tone: rank.event_friend_signal_count || rank.event_social_score >= 0.5 ? 'positive' : 'neutral',
                    }
                    : null,
                  typeof rank.swap_safety_score === 'number' && (rank.swap_stop_count || 0) > 0
                    ? {
                      key: 'swap-safety',
                      label: 'Swaps',
                      value: `${rank.swap_low_friction_count || 0}/${rank.swap_stop_count || 0} easy`,
                      tone: rank.swap_safety_score >= 0.65 && !(rank.swap_route_risk_count || 0)
                        ? 'positive'
                        : (rank.swap_route_risk_count || 0) > 0 || (rank.swap_cost_caution_count || 0) > 0
                          ? 'caution'
                          : 'neutral',
                    }
                    : null,
                  (rank.swap_cost_saving_count || 0) > 0
                    ? {
                      key: 'swap-savings',
                      label: 'Cheaper swaps',
                      value: String(rank.swap_cost_saving_count),
                      tone: 'positive',
                    }
                    : (rank.swap_cost_caution_count || 0) > 0
                      ? {
                        key: 'swap-cost',
                        label: 'Pricier swaps',
                        value: String(rank.swap_cost_caution_count),
                        tone: 'caution',
                      }
                      : null,
                  rank.planning_burden_level
                    ? {
                      key: 'planning',
                      label: 'Planning',
                      value: String(rank.planning_burden_level).toLowerCase(),
                      tone: (rank.planning_burden_score || 0) >= 0.5 ? 'caution' : 'positive',
                    }
                    : null,
                  groupFit?.member_count && groupFit.member_count > 1 && !(rank.friend_member_count && rank.friend_member_count > 1)
                    ? {
                      key: 'party',
                      label: 'Party',
                      value: `${Math.round((rank.group_fairness_score || groupFit.fairness_score || rank.party_score || 0) * 100)}%`,
                      tone: groupFit.underserved_count ? 'caution' : 'positive',
                    }
                    : null,
                  typeof rank.booking_actionable_score === 'number' && rank.booking_actionable_score > 0
                    ? {
                      key: 'bookable',
                      label: 'Bookable',
                      value: `${Math.round(rank.booking_actionable_score * 100)}%`,
                      tone: rank.booking_actionable_score >= 0.75 ? 'positive' : 'neutral',
                    }
                    : typeof rank.booking_score === 'number' && rank.booking_score > 0
                      ? {
                        key: 'booking',
                        label: 'Booking',
                        value: `${Math.round(rank.booking_score * 100)}%`,
                        tone: rank.booking_score >= 0.75 ? 'positive' : 'neutral',
                      }
                      : null,
                  typeof rank.booking_action_link_count === 'number' && rank.booking_action_link_count > 0
                    ? {
                      key: 'booking-links',
                      label: 'Links',
                      value: String(rank.booking_action_link_count),
                      tone: rank.booking_action_link_count >= 2 ? 'positive' : 'neutral',
                    }
                    : null,
                  typeof rank.booking_saveable_item_count === 'number' && rank.booking_saveable_item_count > 0
                    ? {
                      key: 'saveable',
                      label: 'Save',
                      value: String(rank.booking_saveable_item_count),
                      tone: 'positive',
                    }
                    : null,
                ].filter(Boolean) as { key: string; label: string; value: string; tone: string }[];
                return (
                  <View key={comparison.scoring_profile} style={[styles.comparisonRow, isRecommended && styles.comparisonRowRecommended]}>
                    <View style={styles.comparisonText}>
                      <Text style={styles.comparisonName}>
                        {style.label}{isRecommended ? ' pick' : ''}
                      </Text>
                      <Text style={styles.comparisonMeta} numberOfLines={2}>
                        {readiness?.label || 'Route check'} - {Math.round((readiness?.score || 0) * 100)}%
                        {readiness ? ` - ${readiness.planned_stop_count}/${readiness.expected_stop_count} stops` : ''}
                        {comparison.first_stop?.name ? ` - starts at ${comparison.first_stop.name}` : ''}
                      </Text>
                      {scenarioReadiness ? (
                        <View style={styles.comparisonCueRow}>
                          <Text
                            style={[
                              styles.comparisonCuePill,
                              scenarioReadiness.status === 'ready' && styles.comparisonCueReady,
                              scenarioReadiness.status === 'needs_attention' && styles.comparisonCueBlocked,
                            ]}
                          >
                            {scenarioLabel}
                          </Text>
                          <Text style={styles.comparisonCueText} numberOfLines={1}>
                            {scenarioReadiness.headline || 'Adventour checked friend-test readiness.'}
                          </Text>
                        </View>
                      ) : null}
                      {launchChecklist ? (
                        <View style={styles.comparisonCueRow}>
                          <Text
                            style={[
                              styles.comparisonCuePill,
                              launchChecklist.can_start ? styles.comparisonCueReady : styles.comparisonCueBlocked,
                            ]}
                          >
                            {launchChecklist.can_start ? 'Startable' : 'Needs route'}
                          </Text>
                          <Text style={styles.comparisonCueText} numberOfLines={1}>
                            {launchChecklist.can_start
                              ? (launchChecklist.headline || 'No launch blockers.')
                              : `${checklistIssueCount || 1} launch fix${checklistIssueCount === 1 ? '' : 'es'} before starting.`}
                          </Text>
                        </View>
                      ) : null}
                      {explanation?.headline ? (
                        <Text style={styles.comparisonHeadline} numberOfLines={2}>
                          {explanation.headline}
                        </Text>
                      ) : null}
                      {comparisonSignals.length ? (
                        <View style={styles.comparisonSignalRow}>
                          {comparisonSignals.map((signal) => (
                            <Text
                              key={`${comparison.scoring_profile}-${signal.key}`}
                              style={[
                                styles.comparisonSignalPill,
                                signal.tone === 'positive' && styles.comparisonSignalPositive,
                                signal.tone === 'caution' && styles.comparisonSignalCaution,
                              ]}
                            >
                              {signal.label}: {signal.value}
                            </Text>
                          ))}
                        </View>
                      ) : null}
                      {explanation?.tradeoffs?.length ? (
                        <View style={styles.comparisonTradeoffRow}>
                          {explanation.tradeoffs.slice(0, 4).map((tradeoff) => (
                            <Text
                              key={`${comparison.scoring_profile}-${tradeoff.kind}-${tradeoff.label}`}
                              style={[
                                styles.comparisonTradeoffPill,
                                tradeoff.tone === 'positive' && styles.comparisonTradeoffPositive,
                                tradeoff.tone === 'caution' && styles.comparisonTradeoffCaution,
                              ]}
                            >
                              {tradeoff.label}: {tradeoff.value}
                            </Text>
                          ))}
                        </View>
                      ) : null}
                      {hasFriendRouteFit || hasGroupRouteFit ? (
                        <Text
                          style={[
                            styles.comparisonGroupNote,
                            routePartyCaution ? styles.comparisonGroupNoteCaution : null,
                          ]}
                          numberOfLines={2}
                        >
                          {routePartyMessage}
                          {compromiseBrief?.next_action ? ` ${compromiseBrief.next_action}` : ''}
                        </Text>
                      ) : null}
                    </View>
                    {canUseComparison ? (
                      <TouchableOpacity
                        style={styles.useComparisonButton}
                        onPress={() => useItineraryComparison(comparison)}
                        activeOpacity={0.82}
                      >
                        <Text style={styles.useComparisonText}>Use route</Text>
                      </TouchableOpacity>
                    ) : comparison.scoring_profile !== backendScoringProfileId(scoringProfile) ? (
                      <TouchableOpacity
                        style={styles.useComparisonButton}
                        onPress={() => useItineraryComparison(comparison)}
                        activeOpacity={0.82}
                      >
                        <Text style={styles.useComparisonText}>Use</Text>
                      </TouchableOpacity>
                    ) : (
                      <Text style={styles.currentComparisonText}>Current</Text>
                    )}
                  </View>
                );
              })}
            </View>
          ) : null}
        </View>

        {renderDestinationScout()}
        </>
        ) : null}

        {tripSetupOpen ? (
        <View
          style={styles.tripContextPanel}
          onLayout={(event) => setTripDetailsOffsetY(event.nativeEvent.layout.y)}
        >
          <Text style={styles.tripContextTitle}>Trip details</Text>
          <Text style={styles.tripContextHelp}>
            Optional now. Adventour can launch without this, then use it later for flights, stays, events, and saved confirmations.
          </Text>
          <TextInput
            style={styles.tripContextInput}
            value={tripOrigin}
            onChangeText={handleTripOriginChange}
            placeholder="Leaving from, e.g. Orlando, FL"
          />
          {originSuggestions.length > 0 ? (
            <View style={styles.tripOriginSuggestionsList}>
              {originSuggestions.map((item) => (
                <TouchableOpacity
                  key={item.place_id || item.description}
                  style={styles.suggestionItem}
                  onPress={() => handleOriginSuggestionSelect(item.description)}
                >
                  <Text style={styles.suggestionText}>{item.description}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
          <View style={styles.tripDateRow}>
            <TouchableOpacity
              style={[styles.tripDatePickerButton, calendarPicker === 'start' && styles.tripDatePickerButtonActive]}
              onPress={() => setCalendarPicker((current) => current === 'start' ? null : 'start')}
              activeOpacity={0.84}
            >
              <Text style={[styles.tripDatePickerLabel, calendarPicker === 'start' && styles.tripDatePickerLabelActive]}>Start</Text>
              <Text style={[styles.tripDatePickerValue, calendarPicker === 'start' && styles.tripDatePickerValueActive]}>{tripStartDate || 'Pick date'}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.tripDatePickerButton, calendarPicker === 'end' && styles.tripDatePickerButtonActive]}
              onPress={() => setCalendarPicker((current) => current === 'end' ? null : 'end')}
              activeOpacity={0.84}
            >
              <Text style={[styles.tripDatePickerLabel, calendarPicker === 'end' && styles.tripDatePickerLabelActive]}>End</Text>
              <Text style={[styles.tripDatePickerValue, calendarPicker === 'end' && styles.tripDatePickerValueActive]}>{tripEndDate || 'Pick date'}</Text>
            </TouchableOpacity>
          </View>
          {renderTripCalendar()}
          <View style={styles.tripDateShortcutRow}>
            {DATE_SHORTCUTS.map((shortcut) => (
              <TouchableOpacity
                key={shortcut.id}
                style={styles.tripDateShortcutChip}
                onPress={() => applyDateShortcut(shortcut.id)}
                activeOpacity={0.82}
              >
                <Text style={styles.tripDateShortcutText}>{shortcut.label}</Text>
              </TouchableOpacity>
            ))}
            {(tripStartDate || tripEndDate) ? (
              <TouchableOpacity
                style={[styles.tripDateShortcutChip, styles.tripDateClearChip]}
                onPress={() => {
                  setTripStartDate('');
                  setTripEndDate('');
                  setItineraryPlan(null);
                }}
                activeOpacity={0.82}
              >
                <Text style={[styles.tripDateShortcutText, styles.tripDateClearText]}>Clear</Text>
              </TouchableOpacity>
            ) : null}
          </View>
          {tripDateError ? (
            <Text style={styles.tripDateError}>{tripDateError}</Text>
          ) : (tripStartDate && tripEndDate) ? (
            <Text style={styles.tripDateReady}>
              {itineraryDayCount} planned day{itineraryDayCount === 1 ? '' : 's'} will guide events, stays, and booking prep.
            </Text>
          ) : null}
          <View style={styles.tripPreferenceBlock}>
            <Text style={styles.tripPreferenceLabel}>Stay style</Text>
            <View style={styles.tripPreferenceRow}>
              {LODGING_OPTIONS.map((option) => {
                const selected = lodgingOption.id === option.id;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={[styles.tripPreferenceChip, selected && styles.tripPreferenceChipSelected]}
                    onPress={() => {
                      setLodgingOption(option);
                      setItineraryPlan(null);
                    }}
                    activeOpacity={0.82}
                  >
                    <Text style={[styles.tripPreferenceText, selected && styles.tripPreferenceTextSelected]}>{option.label}</Text>
                    <Text style={[styles.tripPreferenceHelper, selected && styles.tripPreferenceHelperSelected]}>{option.helper}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
            <TextInput
              style={[styles.tripContextInput, styles.tripNeighborhoodInput]}
              value={stayNeighborhood}
              onChangeText={(value) => {
                setStayNeighborhood(value);
                setItineraryPlan(null);
              }}
              placeholder="Preferred stay area, e.g. Downtown, Williamsburg"
            />
          </View>
          <View style={styles.tripPreferenceBlock}>
            <Text style={styles.tripPreferenceLabel}>Pace</Text>
            <View style={styles.tripPreferenceRow}>
              {PACE_OPTIONS.map((option) => {
                const selected = paceOption.id === option.id;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={[styles.tripPreferenceChip, selected && styles.tripPreferenceChipSelected]}
                    onPress={() => {
                      setPaceOption(option);
                      setItineraryPlan(null);
                    }}
                    activeOpacity={0.82}
                  >
                    <Text style={[styles.tripPreferenceText, selected && styles.tripPreferenceTextSelected]}>{option.label}</Text>
                    <Text style={[styles.tripPreferenceHelper, selected && styles.tripPreferenceHelperSelected]}>{option.helper}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>
          <View style={styles.tripPreferenceBlock}>
            <Text style={styles.tripPreferenceLabel}>Budget</Text>
            <View style={styles.tripPreferenceRow}>
              {BUDGET_OPTIONS.map((option) => {
                const selected = budgetOption.id === option.id;
                return (
                  <TouchableOpacity
                    key={option.id}
                    style={[styles.tripPreferenceChip, selected && styles.tripPreferenceChipSelected]}
                    onPress={() => {
                      setBudgetOption(option);
                      setItineraryPlan(null);
                    }}
                    activeOpacity={0.82}
                  >
                    <Text style={[styles.tripPreferenceText, selected && styles.tripPreferenceTextSelected]}>{option.label}</Text>
                    <Text style={[styles.tripPreferenceHelper, selected && styles.tripPreferenceHelperSelected]}>{option.helper}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          </View>
        </View>
        ) : null}

        {itineraryPlan ? (
          <>
            {routeDiagnostic ? (
              <View style={styles.planDiagnosticPanel}>
                <Text style={styles.planDiagnosticTitle}>{routeDiagnostic.title}</Text>
                <Text style={styles.planDiagnosticText}>{routeDiagnostic.message}</Text>
              </View>
            ) : null}

            {itineraryScenarioReadiness ? (
              <View style={styles.readinessPanel}>
                <View style={styles.readinessHeader}>
                  <View style={styles.readinessTitleBlock}>
                    <Text style={styles.readinessKicker}>Trip test check</Text>
                    <Text style={styles.readinessTitle}>
                      {itineraryScenarioReadiness.headline || 'Adventour checked this route for friend testing.'}
                    </Text>
                  </View>
                  <Text style={[
                    styles.basketQualityStatus,
                    itineraryScenarioReadiness.status === 'ready' && styles.basketQualityStatusReady,
                    itineraryScenarioReadiness.status === 'needs_attention' && styles.basketQualityStatusAttention,
                  ]}>
                    {itineraryScenarioStatus}
                  </Text>
                </View>
                <View style={styles.basketQualityMetricRow}>
                  {typeof itineraryScenarioReadiness.metrics?.stop_coverage === 'number' ? (
                    <Text style={styles.basketQualityMetric}>
                      {Math.round(itineraryScenarioReadiness.metrics.stop_coverage * 100)}% slots
                    </Text>
                  ) : null}
                  {typeof itineraryScenarioReadiness.metrics?.swap_coverage === 'number' ? (
                    <Text style={styles.basketQualityMetric}>
                      {Math.round(itineraryScenarioReadiness.metrics.swap_coverage * 100)}% swaps
                    </Text>
                  ) : null}
                  {typeof itineraryScenarioReadiness.metrics?.booking_score === 'number' ? (
                    <Text style={styles.basketQualityMetric}>
                      {Math.round(itineraryScenarioReadiness.metrics.booking_score * 100)}% booking
                    </Text>
                  ) : null}
                  {typeof itineraryScenarioReadiness.metrics?.event_score === 'number' ? (
                    <Text style={styles.basketQualityMetric}>
                      {Math.round(itineraryScenarioReadiness.metrics.event_score * 100)}% events
                    </Text>
                  ) : null}
                  {typeof itineraryScenarioReadiness.metrics?.event_social_score === 'number' ? (
                    <Text style={[
                      styles.basketQualityMetric,
                      itineraryScenarioReadiness.metrics.event_social_score >= 0.5 && styles.readinessMetricPillReady,
                    ]}>
                      {Math.round(itineraryScenarioReadiness.metrics.event_social_score * 100)}% social
                    </Text>
                  ) : null}
                  {itineraryBoostLabels.length ? (
                    <Text style={[styles.basketQualityMetric, styles.basketQualityMetricActive]}>
                      Friend-tuned: {itineraryBoostLabels.join(', ')}
                    </Text>
                  ) : null}
                </View>
                {itineraryTestVerdict ? (
                  <View style={styles.testVerdictBox}>
                    <View style={styles.testVerdictHeader}>
                      <View style={styles.testVerdictTitleBlock}>
                        <Text style={styles.testVerdictKicker}>Friend-test verdict</Text>
                        <Text style={styles.testVerdictTitle} numberOfLines={2}>
                          {itineraryTestVerdict.headline || 'Adventour checked this route against friend-testing signals.'}
                        </Text>
                      </View>
                      {typeof itineraryTestVerdict.score === 'number' ? (
                        <Text style={[
                          styles.testVerdictScore,
                          itineraryTestVerdict.status === 'ready' && styles.testVerdictScoreReady,
                          itineraryTestVerdict.status === 'needs_attention' && styles.testVerdictScoreAttention,
                        ]}>
                          {Math.round(itineraryTestVerdict.score * 100)}%
                        </Text>
                      ) : null}
                    </View>
                    {visibleTestVerdictDimensions.length ? (
                      <View style={styles.testVerdictDimensionRow}>
                        {visibleTestVerdictDimensions.map((dimension, index) => (
                          <Text
                            key={`${dimension.name || dimension.label || 'dimension'}-${index}`}
                            style={[
                              styles.testVerdictDimension,
                              dimension.status === 'pass' && styles.testVerdictDimensionReady,
                              dimension.status === 'fail' && styles.testVerdictDimensionAttention,
                            ]}
                          >
                            {dimension.label || dimension.name} {typeof dimension.score === 'number' ? `${Math.round(dimension.score * 100)}%` : ''}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {(itineraryTestVerdict.blockers?.[0] || itineraryTestVerdict.next_actions?.[0]) ? (
                      <Text style={[
                        styles.testVerdictAction,
                        itineraryTestVerdict.blockers?.length ? styles.basketQualityWarning : null,
                      ]} numberOfLines={2}>
                        {itineraryTestVerdict.blockers?.[0] || itineraryTestVerdict.next_actions?.[0]}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {itineraryTopRemediationAction ? (
                  <View style={styles.testVerdictBox}>
                    <View style={styles.testVerdictHeader}>
                      <View style={styles.testVerdictTitleBlock}>
                        <Text style={styles.testVerdictKicker}>Next repair</Text>
                        <Text style={styles.testVerdictTitle} numberOfLines={2}>
                          {itineraryTopRemediation?.label || 'Recommended fix'}
                        </Text>
                      </View>
                      <Text style={[
                        styles.testVerdictScore,
                        itineraryTopRemediation?.severity === 'needs_attention'
                          ? styles.testVerdictScoreAttention
                          : styles.testVerdictScoreWarning,
                      ]}>
                        {itineraryTopRemediation?.severity === 'needs_attention' ? 'Fix' : 'Tune'}
                      </Text>
                    </View>
                    <Text style={[
                      styles.testVerdictAction,
                      itineraryTopRemediation?.severity === 'needs_attention' ? styles.basketQualityWarning : null,
                    ]} numberOfLines={2}>
                      {itineraryTopRemediationAction}
                    </Text>
                    {itineraryTopRemediationAdjustment ? (
                      <Text style={styles.testVerdictAction} numberOfLines={1}>
                        {itineraryTopRemediationAdjustment}
                      </Text>
                    ) : null}
                    {itineraryTopRemediation?.adjustment?.kind === 'rerun_recommendations'
                    || itineraryTopRemediation?.adjustment?.kind === 'collect_trip_inputs'
                    || itineraryTopRemediation?.adjustment?.kind === 'scout_local_events'
                    || itineraryTopRemediation?.adjustment?.kind === 'collect_event_social_signal'
                    || itineraryTopRemediation?.adjustment?.kind === 'collect_booking_details' ? (
                      <TouchableOpacity
                        style={[styles.repairApplyButton, itineraryLoading && styles.planButtonDisabled]}
                        onPress={() => applyItineraryRepair(itineraryTopRemediation.adjustment)}
                        disabled={itineraryLoading}
                        activeOpacity={0.84}
                      >
                        {itineraryLoading ? (
                          <ActivityIndicator color="#123c69" size="small" />
                        ) : (
                          <Text style={styles.repairApplyButtonText}>
                            {itineraryTopRemediation.adjustment.kind === 'collect_trip_inputs'
                              ? 'Add trip details'
                              : itineraryTopRemediation.adjustment.kind === 'scout_local_events'
                                ? 'Scout events'
                                : itineraryTopRemediation.adjustment.kind === 'collect_event_social_signal'
                                  ? 'Build social signal'
                                  : itineraryTopRemediation.adjustment.kind === 'collect_booking_details'
                                    ? 'Open booking wallet'
                                    : 'Apply route repair'}
                          </Text>
                        )}
                      </TouchableOpacity>
                    ) : null}
                  </View>
                ) : null}
                {(itineraryScenarioReadiness.warnings?.[0] || itineraryScenarioReadiness.next_actions?.[0] || itineraryScenarioReadiness.strengths?.[0]) ? (
                  <Text style={[
                    styles.basketQualityMessage,
                    (itineraryScenarioReadiness.warnings?.length || itineraryScenarioReadiness.status === 'needs_attention') ? styles.basketQualityWarning : null,
                  ]} numberOfLines={3}>
                    {itineraryScenarioReadiness.warnings?.[0] || itineraryScenarioReadiness.next_actions?.[0] || itineraryScenarioReadiness.strengths?.[0]}
                  </Text>
                ) : null}
                {itineraryFriendReadiness ? (
                  <View style={styles.friendReadinessBox}>
                    <View style={styles.friendReadinessHeader}>
                      <View style={styles.friendReadinessTitleBlock}>
                        <Text style={styles.friendReadinessKicker}>Route party fit</Text>
                        <Text style={styles.friendReadinessTitle}>
                          {itineraryFriendReadiness.headline || 'Adventour checked each traveler across this route.'}
                        </Text>
                      </View>
                      <Text style={[
                        styles.friendReadinessStatus,
                        itineraryFriendReadiness.status === 'ready' && styles.friendReadinessStatusReady,
                        itineraryFriendReadiness.status === 'needs_attention' && styles.friendReadinessStatusAttention,
                      ]}>
                        {itineraryFriendStatusLabel}
                      </Text>
                    </View>
                    <View style={styles.friendReadinessMetricRow}>
                      {typeof itineraryFriendReadiness.coverage_share === 'number' ? (
                        <Text style={styles.friendReadinessMetric}>
                          {Math.round(itineraryFriendReadiness.coverage_share * 100)}% covered
                        </Text>
                      ) : null}
                      {typeof itineraryFriendReadiness.average_group_fit === 'number' ? (
                        <Text style={styles.friendReadinessMetric}>
                          {Math.round(itineraryFriendReadiness.average_group_fit * 100)}% route fit
                        </Text>
                      ) : null}
                      {typeof itineraryFriendReadiness.average_consensus_fit === 'number' ? (
                        <Text style={styles.friendReadinessMetric}>
                          {Math.round(itineraryFriendReadiness.average_consensus_fit * 100)}% group balance
                        </Text>
                      ) : null}
                      {typeof itineraryFriendReadiness.consensus_gap === 'number' && itineraryFriendReadiness.consensus_gap > 0.06 ? (
                        <Text style={[styles.friendReadinessMetric, styles.friendReadinessMetricCaution]}>
                          {Math.round(itineraryFriendReadiness.consensus_gap * 100)}% gap
                        </Text>
                      ) : null}
                      {typeof itineraryFriendReadiness.underserved_count === 'number' && itineraryFriendReadiness.underserved_count > 0 ? (
                        <Text style={[styles.friendReadinessMetric, styles.friendReadinessMetricCaution]}>
                          {itineraryFriendReadiness.underserved_count} needs a stop
                        </Text>
                      ) : null}
                      {typeof itineraryFriendReadiness.cold_start_member_count === 'number' && itineraryFriendReadiness.cold_start_member_count > 0 ? (
                        <Text style={[styles.friendReadinessMetric, styles.friendReadinessMetricCaution]}>
                          {itineraryFriendReadiness.cold_start_member_count} still learning
                        </Text>
                      ) : null}
                    </View>
                    {itineraryFriendReadiness.underserved_members?.length ? (
                      <View style={styles.friendReadinessMemberRow}>
                        {itineraryFriendReadiness.underserved_members.slice(0, 2).map((member, index) => (
                          <Text
                            key={`${member.user_id || index}-${member.display_name || 'friend'}-route-gap`}
                            style={styles.friendReadinessMemberPill}
                            numberOfLines={1}
                          >
                            {member.display_name || 'Traveler'} {typeof member.best_fit === 'number' ? `${Math.round(member.best_fit * 100)}% best stop` : 'needs a stop'}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {itineraryFriendSuggestionTags.length ? (
                      <View style={styles.friendReadinessMemberRow}>
                        {itineraryFriendSuggestionTags.map((tag) => (
                          <TouchableOpacity
                            key={`route-friend-suggestion-${tag}`}
                            activeOpacity={0.8}
                            onPress={() => applyFriendSuggestionTag(tag)}
                            style={[
                              styles.friendReadinessSuggestionChip,
                              boostedFriendQueryTags.includes(tag) ? styles.friendReadinessSuggestionChipActive : null,
                            ]}
                          >
                            <Text
                              style={[
                                styles.friendReadinessSuggestionText,
                                boostedFriendQueryTags.includes(tag) ? styles.friendReadinessSuggestionTextActive : null,
                              ]}
                              numberOfLines={1}
                            >
                              Try {tag.replace(/_/g, ' ')}
                            </Text>
                          </TouchableOpacity>
                        ))}
                      </View>
                    ) : null}
                    {itineraryFriendAction ? (
                      <Text style={styles.friendReadinessAction} numberOfLines={2}>
                        {itineraryFriendAction}
                      </Text>
                    ) : null}
                    {itineraryFriendSwap ? (
                      <Text style={styles.friendReadinessAction} numberOfLines={2}>
                        Try: {itineraryFriendSwap.from_stop || 'current stop'} {'->'} {itineraryFriendSwap.to_stop || 'suggested swap'}
                        {typeof itineraryFriendSwap.fit === 'number' ? ` (${Math.round(itineraryFriendSwap.fit * 100)}% match)` : ''}
                        {Math.max(
                          optionalNumber(itineraryFriendSwap.group_consensus_delta),
                          optionalNumber(itineraryFriendSwap.group_consensus_gap_delta),
                        ) >= 0.04 ? ` - group balance ${formatSignedDeltaPercent(Math.max(
                          optionalNumber(itineraryFriendSwap.group_consensus_delta),
                          optionalNumber(itineraryFriendSwap.group_consensus_gap_delta),
                        ))}` : ''}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {itineraryPipelineDiagnostic ? (
                  <View style={styles.testVerdictBox}>
                    <View style={styles.testVerdictHeader}>
                      <View style={styles.testVerdictTitleBlock}>
                        <Text style={styles.testVerdictKicker}>Pipeline read</Text>
                        <Text style={styles.testVerdictTitle} numberOfLines={2}>
                          {itineraryPipelineDiagnostic.headline || 'Adventour checked where this route search got stronger or weaker.'}
                        </Text>
                      </View>
                      {itineraryPipelineDiagnostic.primary_issue?.status ? (
                        <Text style={[
                          styles.testVerdictScore,
                          itineraryPipelineDiagnostic.primary_issue.status === 'warn' && styles.testVerdictScoreWarning,
                          itineraryPipelineDiagnostic.primary_issue.status === 'fail' && styles.testVerdictScoreAttention,
                          itineraryPipelineDiagnostic.primary_issue.status === 'pass' && styles.testVerdictScoreReady,
                        ]}>
                          {itineraryPipelineDiagnostic.primary_issue.status === 'fail' ? 'Fix' : itineraryPipelineDiagnostic.primary_issue.status === 'warn' ? 'Tune' : 'OK'}
                        </Text>
                      ) : (
                        <Text style={[styles.testVerdictScore, styles.testVerdictScoreReady]}>OK</Text>
                      )}
                    </View>
                    {visibleItineraryPipelineStages.length ? (
                      <View style={styles.testVerdictDimensionRow}>
                        {visibleItineraryPipelineStages.map((stage, index) => (
                          <Text
                            key={`route-pipeline-${stage.name || stage.label || 'stage'}-${index}`}
                            style={[
                              styles.testVerdictDimension,
                              stage.status === 'pass' && styles.testVerdictDimensionReady,
                              stage.status === 'fail' && styles.testVerdictDimensionAttention,
                              stage.status === 'warn' && styles.testVerdictDimensionWarning,
                            ]}
                          >
                            {stage.label || 'Stage'} {typeof stage.score === 'number' ? `${Math.round(stage.score * 100)}%` : ''}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {itineraryPipelineDiagnostic.primary_issue?.summary ? (
                      <Text style={styles.testVerdictAction} numberOfLines={2}>
                        {itineraryPipelineDiagnostic.primary_issue.summary}
                      </Text>
                    ) : null}
                    {itineraryPipelineAction ? (
                      <Text style={[
                        styles.testVerdictAction,
                        itineraryPipelineDiagnostic.primary_issue?.status === 'fail' ? styles.basketQualityWarning : null,
                      ]} numberOfLines={2}>
                        {itineraryPipelineAction}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
              </View>
            ) : null}

            {itineraryPlan.route_readiness ? (
              <View style={styles.readinessPanel}>
                <View style={styles.readinessHeader}>
                  <View>
                    <Text style={styles.readinessKicker}>Route readiness</Text>
                    <Text style={styles.readinessTitle}>
                      {itineraryPlan.route_readiness.label} - {Math.round(itineraryPlan.route_readiness.score * 100)}%
                    </Text>
                  </View>
                  <Text style={styles.readinessStops}>
                    {itineraryPlan.route_readiness.planned_stop_count}/{itineraryPlan.route_readiness.expected_stop_count} stops
                  </Text>
                </View>
                <View style={styles.readinessMetricRow}>
                  {typeof itineraryPlan.route_readiness.authenticity_score === 'number' ? (
                    <Text style={styles.readinessMetricPill}>
                      Local {Math.round(itineraryPlan.route_readiness.authenticity_score * 100)}%
                    </Text>
                  ) : null}
                  {typeof itineraryPlan.route_readiness.event_score === 'number' ? (
                    <Text style={styles.readinessMetricPill}>
                      Events {Math.round(itineraryPlan.route_readiness.event_score * 100)}%
                    </Text>
                  ) : null}
                  {typeof itineraryPlan.route_readiness.event_social_score === 'number' ? (
                    <Text style={[
                      styles.readinessMetricPill,
                      (itineraryPlan.route_readiness.event_social_score || 0) >= 0.5 && styles.readinessMetricPillReady,
                    ]}>
                      Social {(itineraryPlan.route_readiness.event_summary?.route_friend_signal_count || 0) > 0
                        ? `${itineraryPlan.route_readiness.event_summary?.route_friend_signal_count} friend${itineraryPlan.route_readiness.event_summary?.route_friend_signal_count === 1 ? '' : 's'}`
                        : `${Math.round(itineraryPlan.route_readiness.event_social_score * 100)}%`}
                    </Text>
                  ) : null}
                </View>
                {itineraryPlan.route_readiness.strengths?.length ? (
                  <View style={styles.readinessPillRow}>
                    {itineraryPlan.route_readiness.strengths.slice(0, 2).map((strength) => (
                      <Text key={strength} style={styles.readinessStrengthPill}>{strength}</Text>
                    ))}
                  </View>
                ) : null}
                {itineraryPlan.route_readiness.warnings?.length ? (
                  <Text style={styles.readinessWarning}>
                    {itineraryPlan.route_readiness.warnings.slice(0, 2).join(' ')}
                  </Text>
                ) : null}
              </View>
            ) : null}

            {routeAuthenticity ? (
              <View style={[
                styles.authenticityPanel,
                routeAuthenticity.status === 'ready' && styles.authenticityPanelReady,
                routeAuthenticity.status === 'needs_attention' && styles.authenticityPanelAttention,
              ]}>
                <View style={styles.authenticityHeader}>
                  <View style={styles.authenticityTitleBlock}>
                    <Text style={styles.authenticityKicker}>Local authenticity</Text>
                    <Text style={styles.authenticityTitle} numberOfLines={2}>
                      {routeAuthenticity.headline || 'Adventour checked whether this route feels local-first.'}
                    </Text>
                  </View>
                  {typeof routeAuthenticity.score === 'number' ? (
                    <Text style={[
                      styles.authenticityScore,
                      routeAuthenticity.status === 'ready' && styles.authenticityScoreReady,
                      routeAuthenticity.status === 'needs_attention' && styles.authenticityScoreAttention,
                    ]}>
                      {Math.round(routeAuthenticity.score * 100)}%
                    </Text>
                  ) : null}
                </View>
                <View style={styles.authenticityMetricRow}>
                  <Text style={styles.authenticityMetric}>
                    {routeAuthenticity.local_feeling_count || 0}/{routeAuthenticity.stop_count || 0} local
                  </Text>
                  <Text style={styles.authenticityMetric}>
                    {routeAuthenticity.hidden_gem_count || 0} gems
                  </Text>
                  <Text style={[
                    styles.authenticityMetric,
                    (routeAuthenticity.generic_risk_count || 0) > 0 && styles.authenticityMetricCaution,
                  ]}>
                    {routeAuthenticity.generic_risk_count || 0} generic risk
                  </Text>
                  {(routeAuthenticity.thin_local_evidence_count || 0) > 0 ? (
                    <Text style={[styles.authenticityMetric, styles.authenticityMetricCaution]}>
                      {routeAuthenticity.thin_local_evidence_count} thin proof
                    </Text>
                  ) : typeof routeAuthenticity.average_authenticity_confidence === 'number' ? (
                    <Text style={styles.authenticityMetric}>
                      {Math.round(routeAuthenticity.average_authenticity_confidence * 100)}% proof
                    </Text>
                  ) : null}
                </View>
                {(routeAuthenticity.highlights?.[0] || routeAuthenticity.warnings?.[0] || routeAuthenticity.next_actions?.[0]) ? (
                  <Text style={[
                    styles.authenticityMessage,
                    routeAuthenticity.status === 'needs_attention' ? styles.authenticityWarning : null,
                  ]} numberOfLines={3}>
                    {routeAuthenticity.warnings?.[0] || routeAuthenticity.highlights?.[0] || routeAuthenticity.next_actions?.[0]}
                  </Text>
                ) : null}
                {routeAuthenticity.strongest_local_stops?.length ? (
                  <View style={styles.authenticityStopRow}>
                    {routeAuthenticity.strongest_local_stops.slice(0, 2).map((stop, index) => (
                      <Text
                        key={`${stop.slot_id || stop.name || 'local'}-${index}`}
                        style={styles.authenticityStopPill}
                        numberOfLines={1}
                      >
                        {stop.name || stop.label || 'Local stop'} {typeof stop.authenticity === 'number' ? `${Math.round(stop.authenticity * 100)}%` : ''}
                      </Text>
                    ))}
                  </View>
                ) : null}
              </View>
            ) : null}

            {itineraryStory ? (
              <View style={styles.itineraryStoryPanel}>
                {itineraryStory.headline ? (
                  <Text style={styles.itineraryStoryTitle}>{itineraryStory.headline}</Text>
                ) : null}
                {itineraryStory.narrative ? (
                  <Text style={styles.itineraryStoryNarrative}>{itineraryStory.narrative}</Text>
                ) : null}
                {itineraryStory.badges?.length ? (
                  <View style={styles.itineraryStoryBadgeRow}>
                    {itineraryStory.badges.slice(0, 5).map((badge, index) => (
                      <View
                        key={`${badge.label || 'story'}-${index}`}
                        style={[
                          styles.itineraryStoryBadge,
                          badge.tone === 'ready' && styles.itineraryStoryBadgeReady,
                        ]}
                      >
                        <Text style={[
                          styles.itineraryStoryBadgeLabel,
                          badge.tone === 'ready' && styles.itineraryStoryBadgeLabelReady,
                        ]}>
                          {badge.label}
                        </Text>
                        {badge.detail ? (
                          <Text style={[
                            styles.itineraryStoryBadgeDetail,
                            badge.tone === 'ready' && styles.itineraryStoryBadgeDetailReady,
                          ]}>
                            {badge.detail}
                          </Text>
                        ) : null}
                      </View>
                    ))}
                  </View>
                ) : null}
                {itineraryStory.highlights?.length ? (
                  <View style={styles.itineraryStoryList}>
                    {itineraryStory.highlights.slice(0, 4).map((highlight) => (
                      <View key={highlight} style={styles.itineraryStoryRow}>
                        <Text style={styles.itineraryStoryDot}>+</Text>
                        <Text style={styles.itineraryStoryText}>{highlight}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}
                {itineraryStory.planning_steps?.length ? (
                  <View style={styles.itineraryStoryNextBox}>
                    <Text style={styles.itineraryStoryNextTitle}>Next planning move</Text>
                    <Text style={styles.itineraryStoryNextText}>
                      {itineraryStory.planning_steps[0]}
                    </Text>
                  </View>
                ) : null}
              </View>
            ) : null}

            {itineraryPlan.route_explanation ? (
              <View style={styles.routeExplanationPanel}>
                {itineraryPlan.route_explanation.headline ? (
                  <Text style={styles.routeExplanationTitle}>{itineraryPlan.route_explanation.headline}</Text>
                ) : null}
                {itineraryPlan.route_explanation.reasons?.length ? (
                  <View style={styles.routeExplanationList}>
                    {itineraryPlan.route_explanation.reasons.slice(0, 4).map((reason) => (
                      <View key={reason} style={styles.routeExplanationRow}>
                        <Text style={styles.routeExplanationDot}>-</Text>
                        <Text style={styles.routeExplanationText}>{reason}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}
                {itineraryPlan.route_explanation.stats ? (
                  <View style={styles.routeStatsRow}>
                    <Text style={styles.routeStatPill}>
                      {itineraryPlan.route_explanation.stats.unique_group_count || 0} route types
                    </Text>
                    <Text style={styles.routeStatPill}>
                      {itineraryPlan.route_explanation.stats.route_event_count || 0} paired events
                    </Text>
                    {typeof itineraryPlan.route_explanation.stats.party_score === 'number' ? (
                      <Text style={styles.routeStatPill}>
                        {Math.round(itineraryPlan.route_explanation.stats.party_score * 100)}% party fit
                      </Text>
                    ) : null}
                  </View>
                ) : null}
              </View>
            ) : null}

            {tripPacket ? (
              <View style={[
                styles.tripPacketPanel,
                tripPacket.status === 'ready' && styles.tripPacketPanelReady,
                tripPacket.status === 'blocked' && styles.tripPacketPanelBlocked,
              ]}>
                <View style={styles.tripPacketHeader}>
                  <View style={styles.tripPacketTitleBlock}>
                    <Text style={styles.tripPacketKicker}>Trip packet</Text>
                    <Text style={styles.tripPacketTitle} numberOfLines={2}>
                      {tripPacket.headline || 'Adventour summarized the booking pieces for this route.'}
                    </Text>
                  </View>
                  {typeof tripPacket.booking_score === 'number' ? (
                    <Text style={[
                      styles.tripPacketScore,
                      tripPacket.status === 'ready' && styles.tripPacketScoreReady,
                      tripPacket.status === 'blocked' && styles.tripPacketScoreBlocked,
                    ]}>
                      {Math.round(tripPacket.booking_score * 100)}%
                    </Text>
                  ) : null}
                </View>
                {tripPacket.known_per_person?.label ? (
                  <Text style={styles.tripPacketCost}>
                    {tripPacket.currency || currency} {tripPacket.known_per_person.label}
                  </Text>
                ) : null}
                {(tripPacket.cost_confidence?.tracked_total || tripPacket.quote_plan?.message || tripPacket.cost_confidence?.quote_plan?.message) ? (
                  <Text style={styles.tripPacketCostHint} numberOfLines={2}>
                    {tripPacket.cost_confidence?.tracked_total
                      ? tripPacket.cost_confidence.message
                      : tripPacket.quote_plan?.message || tripPacket.cost_confidence?.quote_plan?.message}
                  </Text>
                ) : null}
                {(tripPacket.quote_plan?.required_count || 0) > 0 ? (
                  <View style={styles.tripPacketCommandMetricRow}>
                    <Text style={[
                      styles.tripPacketCommandMetric,
                      tripPacket.quote_plan?.status === 'ready_to_quote' && styles.modelConfidenceMetricReady,
                    ]}>
                      {tripPacket.quote_plan?.ready_count || 0}/{tripPacket.quote_plan?.required_count || 0} travel quotes ready
                    </Text>
                    {tripPacket.quote_plan?.missing_inputs?.length ? (
                      <Text style={[styles.tripPacketCommandMetric, styles.tripPacketCommandMetricCaution]}>
                        Missing {tripPacket.quote_plan.missing_inputs.slice(0, 2).join(', ')}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.beta_readiness ? (
                  <View style={[
                    styles.betaReadinessPanel,
                    tripPacket.beta_readiness.ready_for_friend_testing && styles.betaReadinessPanelReady,
                    tripPacket.beta_readiness.status === 'not_ready' && styles.betaReadinessPanelBlocked,
                  ]}>
                    <View style={styles.betaReadinessHeader}>
                      <View style={styles.betaReadinessTitleBlock}>
                        <Text style={styles.betaReadinessKicker}>Beta verdict</Text>
                        <Text style={styles.betaReadinessTitle} numberOfLines={2}>
                          {tripPacket.beta_readiness.headline || 'Adventour checked if this trip is ready for close-friend testing.'}
                        </Text>
                      </View>
                      {typeof tripPacket.beta_readiness.score === 'number' ? (
                        <Text style={[
                          styles.betaReadinessScore,
                          tripPacket.beta_readiness.ready_for_friend_testing && styles.betaReadinessScoreReady,
                        ]}>
                          {Math.round(tripPacket.beta_readiness.score * 100)}%
                        </Text>
                      ) : null}
                    </View>
                    {tripPacket.beta_readiness.dimensions?.length ? (
                      <View style={styles.betaReadinessDimensionRow}>
                        {tripPacket.beta_readiness.dimensions.slice(0, 4).map((dimension) => (
                          <Text
                            key={dimension.id || dimension.label}
                            style={[
                              styles.betaReadinessDimension,
                              dimension.status === 'pass' && styles.betaReadinessDimensionPass,
                              dimension.status === 'fail' && styles.betaReadinessDimensionFail,
                            ]}
                          >
                            {dimension.label || dimension.id}: {Math.round((dimension.score || 0) * 100)}%
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {(tripPacket.beta_readiness.weakest_dimension?.label || tripPacket.beta_readiness.next_action) ? (
                      <Text style={styles.betaReadinessAction} numberOfLines={2}>
                        {tripPacket.beta_readiness.weakest_dimension?.label
                          ? `Watch ${tripPacket.beta_readiness.weakest_dimension.label.toLowerCase()}: `
                          : ''}
                        {tripPacket.beta_readiness.next_action}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.booking_command_center ? (
                  <View style={[
                    styles.tripPacketCommandCenter,
                    tripPacket.booking_command_center.status === 'ready' && styles.tripPacketCommandCenterReady,
                    tripPacket.booking_command_center.status === 'needs_details' && styles.tripPacketCommandCenterNeedsDetails,
                  ]}>
                    <View style={styles.tripPacketCommandHeader}>
                      <View style={styles.tripPacketCommandTitleBlock}>
                        <Text style={styles.tripPacketCommandKicker}>Booking command center</Text>
                        <Text style={styles.tripPacketCommandTitle} numberOfLines={2}>
                          {tripPacket.booking_command_center.headline || 'Adventour ordered the booking, setup, and save steps.'}
                        </Text>
                      </View>
                      <Text style={[
                        styles.tripPacketCommandStatus,
                        tripPacket.booking_command_center.status === 'ready' && styles.tripPacketCommandStatusReady,
                      ]}>
                        {tripPacket.booking_command_center.status === 'ready'
                          ? 'Ready'
                          : `${tripPacket.booking_command_center.commands?.length || 0} steps`}
                      </Text>
                    </View>
                    <View style={styles.tripPacketCommandMetricRow}>
                      <Text style={styles.tripPacketCommandMetric}>
                        {tripPacket.booking_command_center.open_link_count || 0} links
                      </Text>
                      <Text style={styles.tripPacketCommandMetric}>
                        {tripPacket.booking_command_center.save_prompt_count || 0} saves
                      </Text>
                      {(tripPacket.booking_command_center.action_needed_count || 0) > 0 ? (
                        <Text style={[styles.tripPacketCommandMetric, styles.tripPacketCommandMetricCaution]}>
                          {tripPacket.booking_command_center.action_needed_count} needed
                        </Text>
                      ) : null}
                    </View>
                    {tripPacket.booking_command_center.commands?.length ? (
                      <View style={styles.tripPacketCommandList}>
                        {tripPacket.booking_command_center.commands.slice(0, 4).map((command, index) => (
                          <View key={`${command.id || command.label || 'command'}-${index}`} style={styles.tripPacketCommandRow}>
                            <Text style={[
                              styles.tripPacketCommandPhase,
                              command.status === 'ready' && styles.tripPacketCommandPhaseReady,
                              command.status === 'action_needed' && styles.tripPacketCommandPhaseNeeded,
                            ]}>
                              {command.phase || 'do'}
                            </Text>
                            <View style={styles.tripPacketCommandTextBlock}>
                              <Text style={styles.tripPacketCommandLabel} numberOfLines={1}>
                                {command.label || 'Review step'}
                              </Text>
                              {(command.action || command.detail || command.provider_label) ? (
                                <Text style={styles.tripPacketCommandDetail} numberOfLines={2}>
                                  {command.action || command.detail || command.provider_label}
                                </Text>
                              ) : null}
                            </View>
                            {(command.source_url || command.can_save) ? (
                              <View style={styles.tripPacketCommandActionRow}>
                                {command.source_url ? (
                                  <TouchableOpacity
                                    style={styles.tripPacketCommandOpen}
                                    onPress={() => command.source_url && Linking.openURL(command.source_url)}
                                    activeOpacity={0.84}
                                  >
                                    <Text style={styles.tripPacketCommandOpenText}>Open</Text>
                                  </TouchableOpacity>
                                ) : null}
                                {command.can_save ? (
                                  <TouchableOpacity
                                    style={[styles.tripPacketCommandOpen, styles.tripPacketCommandSave]}
                                    onPress={() => openReservationDraftFromTripCommand(command)}
                                    activeOpacity={0.84}
                                  >
                                    <Text style={[styles.tripPacketCommandOpenText, styles.tripPacketCommandSaveText]}>Save</Text>
                                  </TouchableOpacity>
                                ) : null}
                              </View>
                            ) : null}
                          </View>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.trip_logistics_readiness ? (
                  <View style={[
                    styles.modelConfidenceBox,
                    tripPacket.trip_logistics_readiness.status === 'ready' && styles.modelConfidenceBoxReady,
                    tripPacket.trip_logistics_readiness.status === 'needs_details' && styles.modelConfidenceBoxCold,
                  ]}>
                    <View style={styles.modelConfidenceHeader}>
                      <View style={styles.modelConfidenceTitleBlock}>
                        <Text style={styles.modelConfidenceKicker}>Trip logistics</Text>
                        <Text style={styles.modelConfidenceTitle} numberOfLines={2}>
                          {tripPacket.trip_logistics_readiness.headline || 'Adventour checked whether travel setup is actionable.'}
                        </Text>
                      </View>
                      {typeof tripPacket.trip_logistics_readiness.score === 'number' ? (
                        <Text style={[
                          styles.modelConfidenceScore,
                          tripPacket.trip_logistics_readiness.status === 'ready' && styles.modelConfidenceScoreReady,
                        ]}>
                          {Math.round(tripPacket.trip_logistics_readiness.score * 100)}%
                        </Text>
                      ) : null}
                    </View>
                    <View style={styles.modelConfidenceMetricRow}>
                      <Text style={styles.modelConfidenceMetric}>
                        {tripPacket.trip_logistics_readiness.quote_ready_count || 0} quotes
                      </Text>
                      <Text style={styles.modelConfidenceMetric}>
                        {tripPacket.trip_logistics_readiness.save_ready_count || 0} saves
                      </Text>
                      <Text style={[
                        styles.modelConfidenceMetric,
                        tripPacket.trip_logistics_readiness.reservation_storage_ready && styles.modelConfidenceMetricReady,
                      ]}>
                        Wallet {tripPacket.trip_logistics_readiness.reservation_storage_ready ? 'ready' : 'manual'}
                      </Text>
                      {tripPacket.trip_logistics_readiness.local_transport_provider ? (
                        <Text style={styles.modelConfidenceMetric}>
                          {tripPacket.trip_logistics_readiness.local_transport_provider}
                        </Text>
                      ) : null}
                      {(tripPacket.trip_logistics_readiness.missing_input_count || 0) > 0 ? (
                        <Text style={[styles.modelConfidenceMetric, styles.modelConfidenceMetricCaution]}>
                          {tripPacket.trip_logistics_readiness.missing_input_count} missing
                        </Text>
                      ) : null}
                    </View>
                    {(tripPacket.trip_logistics_readiness.warnings?.[0] || tripPacket.trip_logistics_readiness.next_actions?.[0]) ? (
                      <Text style={[
                        styles.modelConfidenceAction,
                        tripPacket.trip_logistics_readiness.warnings?.length ? styles.modelConfidenceActionWarning : null,
                      ]} numberOfLines={2}>
                        {tripPacket.trip_logistics_readiness.warnings?.[0] || tripPacket.trip_logistics_readiness.next_actions?.[0]}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.quick_stats?.length ? (
                  <View style={styles.tripPacketStatRow}>
                    {tripPacket.quick_stats.slice(0, 6).map((stat, index) => (
                      <Text
                        key={`${stat.id || stat.label || 'stat'}-${index}`}
                        style={[
                          styles.tripPacketStat,
                          stat.status === 'ready' && styles.tripPacketStatReady,
                          stat.status === 'manual' && styles.tripPacketStatManual,
                        ]}
                      >
                        {stat.label}: {stat.value ?? '--'}
                      </Text>
                    ))}
                  </View>
                ) : null}
                {tripPacket.reservation_coverage ? (
                  <View style={[
                    styles.tripPacketReservationWallet,
                    (tripPacket.reservation_coverage.missing_labels?.length || 0) === 0 && styles.tripPacketReservationWalletReady,
                  ]}>
                    <View style={styles.tripPacketReservationWalletHeader}>
                      <View style={styles.tripPacketReservationWalletTitleBlock}>
                        <Text style={styles.tripPacketReservationWalletKicker}>Reservation wallet</Text>
                        <Text style={styles.tripPacketReservationWalletTitle} numberOfLines={2}>
                          {tripPacket.reservation_coverage.summary?.message || 'Saved confirmations travel with this Adventour.'}
                        </Text>
                      </View>
                      <Text style={[
                        styles.tripPacketReservationWalletScore,
                        (tripPacket.reservation_coverage.missing_labels?.length || 0) === 0 && styles.tripPacketReservationWalletScoreReady,
                      ]}>
                        {tripPacket.reservation_coverage.saved_count || 0}/
                        {tripPacket.reservation_coverage.required_count || tripPacket.reservation_coverage.attached_count || 0}
                      </Text>
                    </View>
                    <View style={styles.tripPacketReservationWalletMetricRow}>
                      <Text style={styles.tripPacketReservationWalletMetric}>
                        {tripPacket.reservation_coverage.attached_count || tripPacket.reservation_coverage.summary?.reservation_count || 0} attached
                      </Text>
                      <Text style={styles.tripPacketReservationWalletMetric}>
                        {tripPacket.reservation_coverage.confirmed_count || tripPacket.reservation_coverage.summary?.confirmation_count || 0} confirmed
                      </Text>
                      {typeof tripPacket.reservation_coverage.summary?.known_cost_per_person === 'number' ? (
                        <Text style={styles.tripPacketReservationWalletMetric}>
                          {tripPacket.reservation_coverage.summary.currency || tripPacket.currency || 'USD'} ${tripPacket.reservation_coverage.summary.known_cost_per_person}/person
                        </Text>
                      ) : null}
                    </View>
                    {tripPacket.reservation_coverage.missing_labels?.length ? (
                      <Text style={styles.tripPacketReservationWalletAction} numberOfLines={2}>
                        Missing: {tripPacket.reservation_coverage.missing_labels.slice(0, 3).join(', ')}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {routeModelConfidence ? (
                  <View style={[
                    styles.modelConfidenceBox,
                    routeModelConfidence.status === 'ready' && styles.modelConfidenceBoxReady,
                    routeModelConfidence.status === 'cold_start' && styles.modelConfidenceBoxCold,
                  ]}>
                    <View style={styles.modelConfidenceHeader}>
                      <View style={styles.modelConfidenceTitleBlock}>
                        <Text style={styles.modelConfidenceKicker}>Route model signal</Text>
                        <Text style={styles.modelConfidenceTitle} numberOfLines={2}>
                          {routeModelConfidence.headline || 'Adventour checked how much to trust this planned route.'}
                        </Text>
                      </View>
                      {typeof routeModelConfidence.score === 'number' ? (
                        <Text style={[
                          styles.modelConfidenceScore,
                          routeModelConfidence.status === 'ready' && styles.modelConfidenceScoreReady,
                        ]}>
                          {Math.round(routeModelConfidence.score * 100)}%
                        </Text>
                      ) : null}
                    </View>
                    <View style={styles.modelConfidenceMetricRow}>
                      {typeof routeModelConfidence.stop_coverage === 'number' ? (
                        <Text style={styles.modelConfidenceMetric}>
                          {Math.round(routeModelConfidence.stop_coverage * 100)}% route
                        </Text>
                      ) : null}
                      {typeof routeModelConfidence.authenticity_score === 'number' ? (
                        <Text style={styles.modelConfidenceMetric}>
                          {Math.round(routeModelConfidence.authenticity_score * 100)}% local
                        </Text>
                      ) : null}
                      {typeof routeModelConfidence.party_score === 'number' && (itineraryPlan.member_count || 1) > 1 ? (
                        <Text style={[
                          styles.modelConfidenceMetric,
                          routeModelConfidence.party_score >= 0.7 ? styles.modelConfidenceMetricReady : styles.modelConfidenceMetricCaution,
                        ]}>
                          {Math.round(routeModelConfidence.party_score * 100)}% party
                        </Text>
                      ) : null}
                      {typeof routeModelConfidence.booking_score === 'number' ? (
                        <Text style={styles.modelConfidenceMetric}>
                          {Math.round(routeModelConfidence.booking_score * 100)}% booking
                        </Text>
                      ) : null}
                      {typeof routeModelConfidence.swap_coverage === 'number' ? (
                        <Text style={styles.modelConfidenceMetric}>
                          {Math.round(routeModelConfidence.swap_coverage * 100)}% swaps
                        </Text>
                      ) : null}
                    </View>
                    {routeModelAction ? (
                      <Text style={[
                        styles.modelConfidenceAction,
                        routeModelConfidence.warnings?.length ? styles.modelConfidenceActionWarning : null,
                      ]} numberOfLines={2}>
                        {routeModelAction}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.booking_checklist?.items?.length ? (
                  <View style={styles.tripPacketChecklist}>
                    <View style={styles.tripPacketChecklistHeader}>
                      <Text style={styles.tripPacketChecklistTitle}>Checklist</Text>
                      <Text style={[
                        styles.tripPacketChecklistStatus,
                        tripPacket.booking_checklist.blocking_count ? styles.tripPacketChecklistStatusNeedsDetails : styles.tripPacketChecklistStatusReady,
                      ]}>
                        {tripPacket.booking_checklist.ready_count || 0}/{tripPacket.booking_checklist.items.length} ready
                      </Text>
                    </View>
                    {tripPacket.booking_checklist.items.slice(0, 4).map((item, index) => (
                      <View key={`${item.id || item.label || 'check'}-${index}`} style={styles.tripPacketChecklistRow}>
                        <Text style={[
                          styles.tripPacketChecklistDot,
                          item.status === 'ready' && styles.tripPacketChecklistDotReady,
                          item.status === 'action_needed' && styles.tripPacketChecklistDotAction,
                        ]}>
                          {item.status === 'ready' ? 'OK' : item.status === 'action_needed' ? '!' : '-'}
                        </Text>
                        <Text style={styles.tripPacketChecklistText} numberOfLines={2}>
                          {item.label}{item.detail ? ` - ${item.detail}` : ''}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
                {tripPacket.authenticity_packet ? (
                  <View style={[
                    styles.tripPacketAuthenticity,
                    tripPacket.authenticity_packet.status === 'ready' && styles.tripPacketAuthenticityReady,
                    tripPacket.authenticity_packet.status === 'needs_attention' && styles.tripPacketAuthenticityAttention,
                  ]}>
                    <View style={styles.tripPacketAuthenticityHeader}>
                      <View style={styles.tripPacketAuthenticityTitleBlock}>
                        <Text style={styles.tripPacketAuthenticityKicker}>Local promise</Text>
                        <Text style={styles.tripPacketAuthenticityTitle} numberOfLines={2}>
                          {tripPacket.authenticity_packet.headline || 'Adventour checked if this route feels local-first.'}
                        </Text>
                      </View>
                      {typeof tripPacket.authenticity_packet.score === 'number' ? (
                        <Text style={[
                          styles.tripPacketAuthenticityScore,
                          tripPacket.authenticity_packet.status === 'ready' && styles.tripPacketAuthenticityScoreReady,
                        ]}>
                          {Math.round(tripPacket.authenticity_packet.score * 100)}%
                        </Text>
                      ) : null}
                    </View>
                    <View style={styles.tripPacketAuthenticityMetricRow}>
                      <Text style={styles.tripPacketAuthenticityMetric}>
                        {tripPacket.authenticity_packet.local_feeling_count || 0}/{tripPacket.authenticity_packet.stop_count || 0} local
                      </Text>
                      <Text style={styles.tripPacketAuthenticityMetric}>
                        {tripPacket.authenticity_packet.hidden_gem_count || 0} gems
                      </Text>
                      <Text style={[
                        styles.tripPacketAuthenticityMetric,
                        (tripPacket.authenticity_packet.generic_risk_count || 0) > 0 && styles.tripPacketAuthenticityMetricCaution,
                      ]}>
                        {tripPacket.authenticity_packet.generic_risk_count || 0} generic risk
                      </Text>
                      {(tripPacket.authenticity_packet.thin_local_evidence_count || 0) > 0 ? (
                        <Text style={[styles.tripPacketAuthenticityMetric, styles.tripPacketAuthenticityMetricCaution]}>
                          {tripPacket.authenticity_packet.thin_local_evidence_count} thin proof
                        </Text>
                      ) : typeof tripPacket.authenticity_packet.average_authenticity_confidence === 'number' ? (
                        <Text style={styles.tripPacketAuthenticityMetric}>
                          {Math.round(tripPacket.authenticity_packet.average_authenticity_confidence * 100)}% proof
                        </Text>
                      ) : null}
                    </View>
                    {(tripPacket.authenticity_packet.warnings?.[0] || tripPacket.authenticity_packet.highlights?.[0] || tripPacket.authenticity_packet.next_actions?.[0]) ? (
                      <Text style={styles.tripPacketAuthenticityMessage} numberOfLines={2}>
                        {tripPacket.authenticity_packet.warnings?.[0]
                          || tripPacket.authenticity_packet.highlights?.[0]
                          || tripPacket.authenticity_packet.next_actions?.[0]}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.friend_test_packet ? (
                  <View style={[
                    styles.tripPacketFriendTest,
                    tripPacket.friend_test_packet.friend_testable && styles.tripPacketFriendTestReady,
                    tripPacket.friend_test_packet.status === 'needs_attention' && styles.tripPacketFriendTestAttention,
                  ]}>
                    <View style={styles.tripPacketFriendTestHeader}>
                      <View style={styles.tripPacketFriendTestTitleBlock}>
                        <Text style={styles.tripPacketFriendTestKicker}>Friend test</Text>
                        <Text style={styles.tripPacketFriendTestTitle} numberOfLines={2}>
                          {tripPacket.friend_test_packet.headline || 'Adventour checked whether this route is ready to test with friends.'}
                        </Text>
                      </View>
                      {typeof tripPacket.friend_test_packet.score === 'number' ? (
                        <Text style={[
                          styles.tripPacketFriendTestScore,
                          tripPacket.friend_test_packet.friend_testable && styles.tripPacketFriendTestScoreReady,
                        ]}>
                          {Math.round(tripPacket.friend_test_packet.score * 100)}%
                        </Text>
                      ) : (
                        <Text style={[
                          styles.tripPacketFriendTestStatus,
                          tripPacket.friend_test_packet.friend_testable && styles.tripPacketFriendTestStatusReady,
                        ]}>
                          {tripPacket.friend_test_packet.friend_testable ? 'Ready' : String(tripPacket.friend_test_packet.status || 'Watch').replace(/_/g, ' ')}
                        </Text>
                      )}
                    </View>
                    <View style={styles.tripPacketFriendTestMetricRow}>
                      {typeof tripPacket.friend_test_packet.coverage_share === 'number' ? (
                        <Text style={styles.tripPacketFriendTestMetric}>
                          {Math.round(tripPacket.friend_test_packet.coverage_share * 100)}% covered
                        </Text>
                      ) : null}
                      {typeof tripPacket.friend_test_packet.average_group_fit === 'number' ? (
                        <Text style={styles.tripPacketFriendTestMetric}>
                          {Math.round(tripPacket.friend_test_packet.average_group_fit * 100)}% route fit
                        </Text>
                      ) : null}
                      {typeof tripPacket.friend_test_packet.underserved_count === 'number' && tripPacket.friend_test_packet.underserved_count > 0 ? (
                        <Text style={[styles.tripPacketFriendTestMetric, styles.tripPacketFriendTestMetricCaution]}>
                          {tripPacket.friend_test_packet.underserved_count} needs a stop
                        </Text>
                      ) : null}
                    </View>
                    {tripPacket.friend_test_packet.compromise_brief?.balance_chips?.length ? (
                      <View style={styles.tripPacketFriendTestMetricRow}>
                        {tripPacket.friend_test_packet.compromise_brief.balance_chips.slice(0, 3).map((chip) => (
                          <Text
                            key={`${chip.label}-${chip.value}`}
                            style={[
                              styles.tripPacketFriendTestMetric,
                              chip.tone === 'caution' && styles.tripPacketFriendTestMetricCaution,
                              chip.tone === 'positive' && styles.tripPacketFriendTestMetricPositive,
                            ]}
                          >
                            {chip.label}: {chip.value}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {tripPacket.friend_test_packet.compromise_brief?.headline ? (
                      <Text
                        style={[
                          styles.tripPacketFriendTestMessage,
                          ['needs_coverage', 'uneven'].includes(String(tripPacket.friend_test_packet.compromise_brief.status || ''))
                            ? styles.tripPacketFriendTestMessageCaution
                            : null,
                        ]}
                        numberOfLines={2}
                      >
                        {tripPacket.friend_test_packet.compromise_brief.headline}
                        {tripPacket.friend_test_packet.compromise_brief.next_action
                          ? ` ${tripPacket.friend_test_packet.compromise_brief.next_action}`
                          : ''}
                      </Text>
                    ) : null}
                    {(tripPacket.friend_test_packet.blockers?.[0] || tripPacket.friend_test_packet.next_actions?.[0]) ? (
                      <Text style={[
                        styles.tripPacketFriendTestMessage,
                        tripPacket.friend_test_packet.blockers?.length ? styles.tripPacketFriendTestMessageCaution : null,
                      ]} numberOfLines={2}>
                        {tripPacket.friend_test_packet.blockers?.[0] || tripPacket.friend_test_packet.next_actions?.[0]}
                      </Text>
                    ) : null}
                    {tripPacket.friend_test_packet.suggested_swaps?.[0] ? (
                      <Text style={styles.tripPacketFriendTestSwap} numberOfLines={2}>
                        Try: {tripPacket.friend_test_packet.suggested_swaps[0].from_stop || 'current stop'} {'->'} {tripPacket.friend_test_packet.suggested_swaps[0].to_stop || 'suggested swap'}
                        {typeof tripPacket.friend_test_packet.suggested_swaps[0].fit === 'number'
                          ? ` (${Math.round(tripPacket.friend_test_packet.suggested_swaps[0].fit * 100)}% match)`
                          : ''}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.event_packet ? (
                  <View style={[
                    styles.tripPacketEvent,
                    tripPacket.event_packet.status === 'ready' && styles.tripPacketEventReady,
                    tripPacket.event_packet.status === 'needs_scouting' && styles.tripPacketEventScout,
                  ]}>
                    <View style={styles.tripPacketEventHeader}>
                      <View style={styles.tripPacketEventTitleBlock}>
                        <Text style={styles.tripPacketEventKicker}>Local event anchor</Text>
                        <Text style={styles.tripPacketEventTitle} numberOfLines={2}>
                          {tripPacket.event_packet.headline || 'Adventour checked local events for this route.'}
                        </Text>
                      </View>
                      <Text style={[
                        styles.tripPacketEventStatus,
                        tripPacket.event_packet.status === 'ready' && styles.tripPacketEventStatusReady,
                      ]}>
                        {tripPacket.event_packet.short_label || tripPacket.event_packet.status || 'Scout'}
                      </Text>
                    </View>
                    <View style={styles.tripPacketEventMetricRow}>
                      <Text style={styles.tripPacketEventMetric}>
                        {tripPacket.event_packet.route_match_count || 0} paired
                      </Text>
                      <Text style={styles.tripPacketEventMetric}>
                        {tripPacket.event_packet.reservation_ready_count || 0} RSVP
                      </Text>
                      <Text style={styles.tripPacketEventMetric}>
                        {tripPacket.event_packet.friend_signal_count || 0} friend signal
                      </Text>
                    </View>
                    {tripPacket.event_packet.top_event_title ? (
                      <Text style={styles.tripPacketEventTop} numberOfLines={1}>
                        Anchor: {tripPacket.event_packet.top_event_title}
                      </Text>
                    ) : null}
                    {tripPacket.event_packet.meetup_anchor ? (
                      <View style={styles.tripPacketMeetupAnchor}>
                        <Text style={styles.tripPacketMeetupKicker}>Meetup pick</Text>
                        <Text style={styles.tripPacketMeetupTitle} numberOfLines={1}>
                          {tripPacket.event_packet.meetup_anchor.title || tripPacket.event_packet.top_event_title || 'Local event'}
                        </Text>
                        {tripPacket.event_packet.meetup_anchor.route_context?.fit_label ? (
                          <Text style={styles.tripPacketMeetupRoute} numberOfLines={1}>
                            {tripPacket.event_packet.meetup_anchor.route_context.fit_label}
                            {tripPacket.event_packet.meetup_anchor.route_context.stop_name
                              ? ` near ${tripPacket.event_packet.meetup_anchor.route_context.stop_name}`
                              : ''}
                          </Text>
                        ) : null}
                        {tripPacket.event_packet.meetup_anchor.reason ? (
                          <Text style={styles.tripPacketMeetupReason} numberOfLines={2}>
                            {tripPacket.event_packet.meetup_anchor.reason}
                          </Text>
                        ) : null}
                        {tripPacket.event_packet.meetup_anchor.action_url ? (
                          <TouchableOpacity
                            style={styles.tripPacketMeetupButton}
                            onPress={() => tripPacket.event_packet?.meetup_anchor?.action_url && Linking.openURL(tripPacket.event_packet.meetup_anchor.action_url)}
                            activeOpacity={0.84}
                          >
                            <Text style={styles.tripPacketMeetupButtonText}>
                              {tripPacket.event_packet.meetup_anchor.reservation_ready ? 'Open RSVP' : 'Open event'}
                            </Text>
                          </TouchableOpacity>
                        ) : null}
                      </View>
                    ) : null}
                    {tripPacket.event_packet.next_action ? (
                      <Text style={styles.tripPacketEventAction} numberOfLines={2}>
                        {tripPacket.event_packet.next_action}
                      </Text>
                    ) : null}
                    {tripPacket.event_packet.recommended_source?.url ? (
                      <TouchableOpacity
                        style={styles.tripPacketEventSourceButton}
                        onPress={() => tripPacket.event_packet?.recommended_source?.url && Linking.openURL(tripPacket.event_packet.recommended_source.url)}
                        activeOpacity={0.84}
                      >
                        <Text style={styles.tripPacketEventSourceText}>
                          Open {tripPacket.event_packet.recommended_source.label || 'best event source'}
                        </Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.mobility_setup ? (
                  <View style={styles.tripPacketMobility}>
                    <View style={styles.tripPacketMobilityHeader}>
                      <View style={styles.tripPacketMobilityText}>
                        <Text style={styles.tripPacketMobilityKicker}>Mobility setup</Text>
                        <Text style={styles.tripPacketMobilityTitle} numberOfLines={1}>
                          {tripPacket.mobility_setup.provider_label || tripPacket.mobility_setup.label || 'Local travel setup'}
                        </Text>
                      </View>
                      <View style={styles.tripPacketMobilityButtonRow}>
                        {tripPacket.mobility_setup.source_url ? (
                          <TouchableOpacity
                            style={styles.tripPacketMobilityOpen}
                            onPress={() => tripPacket.mobility_setup?.source_url && Linking.openURL(tripPacket.mobility_setup.source_url)}
                            activeOpacity={0.84}
                          >
                            <Text style={styles.tripPacketMobilityOpenText}>Open</Text>
                          </TouchableOpacity>
                        ) : null}
                        {tripPacket.mobility_setup.can_save !== false ? (
                          <TouchableOpacity
                            style={[styles.tripPacketMobilityOpen, styles.tripPacketMobilitySave]}
                            onPress={() => tripPacket.mobility_setup && openReservationDraftFromMobilitySetup(tripPacket.mobility_setup)}
                            activeOpacity={0.84}
                          >
                            <Text style={[styles.tripPacketMobilityOpenText, styles.tripPacketMobilitySaveText]}>Save</Text>
                          </TouchableOpacity>
                        ) : null}
                      </View>
                    </View>
                    {tripPacket.mobility_setup.estimate ? (
                      <Text style={styles.tripPacketMobilityMeta}>
                        {tripPacket.mobility_setup.label || 'Local travel'}
                        {typeof tripPacket.mobility_setup.estimate.per_person_low === 'number'
                          && typeof tripPacket.mobility_setup.estimate.per_person_high === 'number'
                          ? ` - ${tripPacket.mobility_setup.estimate.currency || tripPacket.currency || 'USD'} $${tripPacket.mobility_setup.estimate.per_person_low}-${tripPacket.mobility_setup.estimate.per_person_high} / person`
                          : ''}
                      </Text>
                    ) : null}
                    {tripPacket.mobility_setup.recommended_option ? (
                      <Text style={styles.tripPacketMobilityOption} numberOfLines={2}>
                        Best fit: {tripPacket.mobility_setup.recommended_option.label}
                        {tripPacket.mobility_setup.recommended_option.why
                          ? ` - ${tripPacket.mobility_setup.recommended_option.why}`
                          : ''}
                      </Text>
                    ) : null}
                    {tripPacket.mobility_setup.route_distance_meters ? (
                      <Text style={styles.tripPacketMobilityDistance}>
                        {formatRouteDistance(tripPacket.mobility_setup.route_distance_meters)}
                      </Text>
                    ) : null}
                    {(tripPacket.mobility_setup.next_step || tripPacket.mobility_setup.setup_steps?.[0]) ? (
                      <Text style={styles.tripPacketMobilityStep} numberOfLines={2}>
                        {tripPacket.mobility_setup.next_step || tripPacket.mobility_setup.setup_steps?.[0]}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {tripPacket.next_step ? (
                  <Text style={styles.tripPacketNext} numberOfLines={2}>
                    Next: {tripPacket.next_step}
                  </Text>
                ) : null}
                {tripPacket.required_actions?.length ? (
                  <View style={styles.tripPacketActionList}>
                    {tripPacket.required_actions.slice(0, 3).map((action, index) => (
                      <View key={`${action.id || action.label || 'action'}-${index}`} style={styles.tripPacketActionRow}>
                        <Text style={styles.tripPacketActionDot}>!</Text>
                        <Text style={styles.tripPacketActionText} numberOfLines={2}>
                          {action.label}{action.detail ? ` - ${action.detail}` : ''}
                        </Text>
                      </View>
                    ))}
                  </View>
                ) : null}
                {tripPacket.booking_links?.length ? (
                  <View style={styles.tripPacketLinkRow}>
                    {tripPacket.booking_links.slice(0, 3).map((link, index) => (
                      <TouchableOpacity
                        key={`${link.id || link.label || 'link'}-${index}`}
                        style={[styles.tripPacketLink, !link.url && styles.tripPacketLinkDisabled]}
                        onPress={() => link.url && Linking.openURL(link.url)}
                        disabled={!link.url}
                        activeOpacity={0.84}
                      >
                        <Text style={styles.tripPacketLinkText} numberOfLines={1}>
                          {link.label || link.provider_label || 'Open'}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : null}
                {tripPacket.save_prompts?.length ? (
                  <View style={styles.tripPacketSaveRow}>
                    {tripPacket.save_prompts.slice(0, 3).map((prompt, index) => (
                      <TouchableOpacity
                        key={`${prompt.id || prompt.label || 'save'}-${index}`}
                        style={styles.tripPacketSavePrompt}
                        onPress={() => openReservationDraftFromTripPrompt(prompt)}
                        activeOpacity={0.84}
                      >
                        <Text style={styles.tripPacketSavePromptKicker}>
                          {prompt.reservation_type === 'event' ? 'Save RSVP' : 'Save details'}
                        </Text>
                        <Text style={styles.tripPacketSavePromptText} numberOfLines={1}>
                          {prompt.label || 'Booking detail'}
                        </Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : null}
              </View>
            ) : null}

            {price ? (
              <View style={styles.priceBand}>
                <Text style={styles.priceLabel}>Known estimate</Text>
                <Text style={styles.priceValue}>
                  {currency} ${price.total_known_low}-${price.total_known_high} / person
                </Text>
                {savedReservationCostTotal > 0 ? (
                  <View style={styles.savedCostBox}>
                    <Text style={styles.savedCostTitle}>Saved booking costs tracked</Text>
                    <Text style={styles.savedCostValue}>
                      {currency} ${savedReservationCostTotal.toFixed(2)} total - {currency} ${savedReservationCostPerPerson.toFixed(2)} / person
                    </Text>
                    {savedReservationEstimateAddOnTotal > 0 ? (
                      <Text style={styles.savedCostCombined}>
                        Known with travel bookings: {currency} ${combinedKnownLow.toFixed(2)}-{combinedKnownHigh.toFixed(2)} / person
                      </Text>
                    ) : (
                      <Text style={styles.savedCostCombined}>
                        Local/place costs are tracked here without double-counting the estimate.
                      </Text>
                    )}
                  </View>
                ) : null}
                <Text style={styles.priceNote}>
                  {itineraryPlan.pace ? `${itineraryPlan.pace} pace` : paceOption.label}
                  {itineraryPlan.price_breakdown?.budget_label ? ` - ${itineraryPlan.price_breakdown.budget_label}` : ` - ${budgetOption.label}`}
                </Text>
                <Text style={styles.priceNote}>
                  {savedReservationCostTotal > 0
                    ? 'Flight, stay, and event bookings update the estimate; local/place costs stay tracked in the wallet.'
                    : 'Flights and stay will connect later through booking providers, or you can save manual booking details now.'}
                </Text>
                {itineraryPlan.price_breakdown?.travelers?.length ? (
                  <View style={styles.travelerCostList}>
                    {itineraryPlan.price_breakdown.travelers.map((traveler, index) => (
                      <View key={`${traveler.user_id ?? 'traveler'}-${index}`} style={styles.travelerCostRow}>
                        <Text style={styles.travelerCostName} numberOfLines={1}>
                          {traveler.display_name}
                        </Text>
                        <Text style={styles.travelerCostValue}>
                          {currency} ${(traveler.known_low + savedReservationEstimateAddOnPerPerson).toFixed(2)}-{(traveler.known_high + savedReservationEstimateAddOnPerPerson).toFixed(2)}
                        </Text>
                      </View>
                    ))}
                    <Text style={styles.travelerCostNote}>
                      Flight, stay, and event costs are split evenly for now; local/place costs stay tracked in the wallet.
                    </Text>
                  </View>
                ) : null}
              </View>
            ) : null}

            {renderBookingPlan()}

            {itinerarySwapGuide ? (
              <View style={[
                styles.swapGuidePanel,
                itinerarySwapGuide.status === 'ready' && styles.swapGuidePanelReady,
                itinerarySwapGuide.status === 'needs_attention' && styles.swapGuidePanelAttention,
              ]}>
                <View style={styles.swapGuideHeader}>
                  <View style={styles.swapGuideTitleBlock}>
                    <Text style={styles.swapGuideKicker}>Swap safety</Text>
                    <Text style={styles.swapGuideTitle} numberOfLines={2}>
                      {itinerarySwapGuide.headline || 'Adventour checked how safely this route can be customized.'}
                    </Text>
                  </View>
                  <Text style={[
                    styles.swapGuideStatus,
                    itinerarySwapGuide.status === 'ready' && styles.swapGuideStatusReady,
                  ]}>
                    {itinerarySwapGuide.status === 'ready' ? 'Flexible' : String(itinerarySwapGuide.status || 'Watch').replace(/_/g, ' ')}
                  </Text>
                </View>
                <View style={styles.swapGuideMetricRow}>
                  <Text style={styles.swapGuideMetric}>
                    {itinerarySwapGuide.swappable_stop_count || 0}/{itinerarySwapGuide.stop_count || 0} swappable
                  </Text>
                  <Text style={styles.swapGuideMetric}>
                    {itinerarySwapGuide.low_friction_count || 0} low-friction
                  </Text>
                  <Text style={styles.swapGuideMetric}>
                    {itinerarySwapGuide.recommended_swap_count || 0} recommended
                  </Text>
                  {(itinerarySwapGuide.party_upgrade_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricReady]}>
                      {itinerarySwapGuide.party_upgrade_count} party boost
                    </Text>
                  ) : null}
                  {(itinerarySwapGuide.consensus_upgrade_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricReady]}>
                      {itinerarySwapGuide.consensus_upgrade_count} group balance
                    </Text>
                  ) : null}
                  {(itinerarySwapGuide.authenticity_upgrade_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricReady]}>
                      {itinerarySwapGuide.authenticity_upgrade_count} local boost
                    </Text>
                  ) : null}
                  {(itinerarySwapGuide.route_risk_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricCaution]}>
                      {itinerarySwapGuide.route_risk_count} route risk
                    </Text>
                  ) : null}
                  {(itinerarySwapGuide.cost_saving_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricReady]}>
                      {itinerarySwapGuide.cost_saving_count} cheaper
                    </Text>
                  ) : null}
                  {(itinerarySwapGuide.cost_caution_count || 0) > 0 ? (
                    <Text style={[styles.swapGuideMetric, styles.swapGuideMetricCaution]}>
                      {itinerarySwapGuide.cost_caution_count} pricier
                    </Text>
                  ) : null}
                </View>
                {itinerarySwapGuide.party_coverage_plan?.headline ? (
                  <View style={styles.swapGuideBestBox}>
                    <Text style={styles.swapGuideBestKicker}>Group coverage</Text>
                    <Text style={styles.swapGuideBestText} numberOfLines={2}>
                      {itinerarySwapGuide.party_coverage_plan.headline}
                    </Text>
                    {itinerarySwapGuide.party_coverage_plan.members?.find((member) => (member.suggested_swaps || []).length)?.suggested_swaps?.[0] ? (
                      <Text style={styles.swapGuideBestReason} numberOfLines={2}>
                        Try {itinerarySwapGuide.party_coverage_plan.members.find((member) => (member.suggested_swaps || []).length)?.suggested_swaps?.[0]?.to_name || 'the suggested swap'}
                        {itinerarySwapGuide.party_coverage_plan.members.find((member) => (member.suggested_swaps || []).length)?.display_name
                          ? ` for ${itinerarySwapGuide.party_coverage_plan.members.find((member) => (member.suggested_swaps || []).length)?.display_name}`
                          : ''}.
                      </Text>
                    ) : itinerarySwapGuide.party_coverage_plan.next_action ? (
                      <Text style={styles.swapGuideBestReason} numberOfLines={2}>
                        {itinerarySwapGuide.party_coverage_plan.next_action}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {itinerarySwapGuide.best_swaps?.[0] ? (
                  <TouchableOpacity
                    style={styles.swapGuideBestBox}
                    onPress={() => applySwapGuideSuggestion(itinerarySwapGuide.best_swaps?.[0])}
                    activeOpacity={0.84}
                  >
                    <Text style={styles.swapGuideBestKicker}>Best swap to preview</Text>
                    <Text style={styles.swapGuideBestText} numberOfLines={2}>
                      {itinerarySwapGuide.best_swaps[0].from_name || 'Current stop'} {'->'} {itinerarySwapGuide.best_swaps[0].to_name || 'swap option'}
                      {typeof itinerarySwapGuide.best_swaps[0].confidence === 'number'
                        ? ` (${Math.round(itinerarySwapGuide.best_swaps[0].confidence * 100)}% confidence)`
                        : ''}
                    </Text>
                    {itinerarySwapGuide.best_swaps[0].best_when ? (
                      <Text style={styles.swapGuideBestReason} numberOfLines={2}>
                        {itinerarySwapGuide.best_swaps[0].best_when}
                      </Text>
                    ) : null}
                    {Math.max(
                      optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_delta),
                      optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_gap_delta),
                    ) >= 0.04 ? (
                      <Text style={styles.swapGuideBestReason} numberOfLines={2}>
                        Helps balance the group
                        {formatSignedDeltaPercent(Math.max(
                          optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_delta),
                          optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_gap_delta),
                        )) ? ` by ${formatSignedDeltaPercent(Math.max(
                          optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_delta),
                          optionalNumber(itinerarySwapGuide.best_swaps[0].group_consensus_gap_delta),
                        ))}` : ''}.
                      </Text>
                    ) : null}
                    <Text style={styles.swapGuideApplyHint}>Tap to apply this swap</Text>
                  </TouchableOpacity>
                ) : null}
                {itinerarySwapGuide.next_action ? (
                  <Text style={styles.swapGuideAction} numberOfLines={2}>
                    {itinerarySwapGuide.next_action}
                  </Text>
                ) : null}
              </View>
            ) : null}

            {itineraryPlan.days.map((day, dayIndex) => (
              <View key={day.day} style={styles.planDay}>
                <Text style={styles.planDayTitle}>{day.title}</Text>
                <Text style={styles.planDaySummary}>{day.summary}</Text>
                {day.route_balance?.unique_groups?.length ? (
                  <View style={styles.routeMixPanel}>
                    <Text style={styles.routeMixTitle}>
                      Route mix {day.route_balance.variety_score ? `(${Math.round(day.route_balance.variety_score * 100)}% variety)` : ''}
                    </Text>
                    <View style={styles.routeMixChips}>
                      {day.route_balance.unique_groups.map((group) => (
                        <View key={group} style={[styles.routeMixChip, { borderColor: routeGroupTone(group) }]}>
                          <Text style={[styles.routeMixChipText, { color: routeGroupTone(group) }]}>
                            {routeGroupLabel(group)}
                          </Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}
                {day.party_fit?.members?.length ? (
                  <View style={styles.partyFitPanel}>
                    <View style={styles.partyFitHeader}>
                      <Text style={styles.partyFitTitle}>
                        Party fit {day.party_fit.fairness_score !== undefined && day.party_fit.fairness_score !== null
                          ? `(${formatFitPercent(day.party_fit.fairness_score)} balanced)`
                          : ''}
                      </Text>
                      <Text style={styles.partyFitMessage}>{day.party_fit.message}</Text>
                    </View>
                    <View style={styles.partyFitRows}>
                      {day.party_fit.members.map((member) => {
                        const hasStrongMatch = member.coverage_status === 'covered' || (member.strong_match_count || 0) > 0;
                        const bestMatch = member.best_match;
                        return (
                          <View
                            key={member.user_id}
                            style={[
                              styles.partyFitPill,
                              !hasStrongMatch && styles.partyFitPillWeak,
                            ]}
                          >
                            <View style={styles.partyFitPillTopRow}>
                              <Text style={styles.partyFitName} numberOfLines={1}>{member.display_name}</Text>
                              <Text style={styles.partyFitScore}>{formatFitPercent(member.average_fit)}</Text>
                            </View>
                            <Text
                              style={[
                                styles.partyFitCoverage,
                                !hasStrongMatch && styles.partyFitCoverageWeak,
                              ]}
                              numberOfLines={1}
                            >
                              {hasStrongMatch && bestMatch?.name
                                ? `Anchor: ${bestMatch.name}`
                                : hasStrongMatch
                                  ? `${member.strong_match_count || 1} strong stop${(member.strong_match_count || 1) === 1 ? '' : 's'}`
                                  : bestMatch?.name
                                    ? `Closest: ${bestMatch.name}`
                                    : 'Needs stronger stop'}
                            </Text>
                          </View>
                        );
                      })}
                    </View>
                  </View>
                ) : null}
                {day.stops.map((stop, index) => {
                  const swapKey = itineraryStopSwapKey(dayIndex, index, stop);
                  const wasSwapped = swappedItinerarySlots.includes(swapKey);
                  const stopPartySummary = stop.party_fit_summary || partyFitSummaryForItineraryRecommendation(stop.recommendation);
                  const stopReasoning = stop.why_this_stop || whyThisStopForItineraryRecommendation(stop, stop.recommendation);
                  const reasonMetrics = stopReasonMetrics(stopReasoning);
                  const stopEventMatches = stop.local_event_matches || [];
                  const friendHistorySignal = friendHistorySignalForItineraryRecommendation(stop.recommendation);
                  return (
                  <View key={`${stop.slot_id}-${stop.recommendation.place_id}`} style={styles.planStop}>
                    <View style={styles.planStopIndex}>
                      <Text style={styles.planStopIndexText}>{index + 1}</Text>
                    </View>
                    <View style={styles.planStopBody}>
                      <Text style={styles.planStopWindow}>{stop.time_window}</Text>
                      <View style={styles.planStopLabelRow}>
                        <Text style={styles.planStopLabel}>{stop.label}</Text>
                        {wasSwapped ? (
                          <Text style={styles.planStopSwappedPill}>Swapped</Text>
                        ) : null}
                        {friendHistorySignal ? (
                          <Text
                            style={[
                              styles.planStopFriendPill,
                              friendHistorySignal.tone === 'caution' && styles.planStopFriendPillCaution,
                            ]}
                            numberOfLines={1}
                          >
                            {friendHistorySignal.label}
                          </Text>
                        ) : null}
                      </View>
                      <Text style={styles.planStopName}>{itineraryPlaceName(stop.recommendation)}</Text>
                      <Text style={styles.planStopAddress} numberOfLines={1}>
                        {itineraryPlaceAddress(stop.recommendation)}
                      </Text>
                      {stopEventMatches.length ? (
                        <View style={styles.stopEventPanel}>
                          <View style={styles.stopEventHeader}>
                            <View style={styles.stopEventTitleBlock}>
                              <Text style={styles.stopEventEyebrow}>Local event nearby</Text>
                              <Text style={styles.stopEventTitle} numberOfLines={1}>
                                {stopEventMatches[0].title || 'Local happening'}
                              </Text>
                            </View>
                            <Text style={[
                              styles.stopEventPill,
                              stopEventMatches[0].reservation_ready && styles.stopEventPillReady,
                            ]}>
                              {stopEventMatches[0].reservation_ready ? 'RSVP' : stopEventMatches[0].source_badge || 'Source'}
                            </Text>
                          </View>
                          <Text style={styles.stopEventMeta} numberOfLines={2}>
                            {[
                              stopEventMatches[0].fit_label,
                              formatEventDistance(stopEventMatches[0].distance_to_stop_meters ?? undefined),
                              stopEventMatches[0].reasons?.[0],
                            ].filter(Boolean).join(' - ')}
                          </Text>
                          {(stopEventMatches[0].reservation_url || stopEventMatches[0].source_url) ? (
                            <TouchableOpacity
                              style={styles.stopEventLink}
                              onPress={() => Linking.openURL((stopEventMatches[0].reservation_url || stopEventMatches[0].source_url)!)}
                              activeOpacity={0.82}
                            >
                              <Text style={styles.stopEventLinkText}>
                                {stopEventMatches[0].reservation_url ? 'Open reservation' : 'Open event source'}
                              </Text>
                            </TouchableOpacity>
                          ) : null}
                        </View>
                      ) : null}
                      {stopReasoning?.reasons?.length ? (
                        <View style={styles.stopReasonPanel}>
                          <Text style={styles.stopReasonTitle}>Why this stop</Text>
                          {reasonMetrics.length ? (
                            <View style={styles.stopReasonMetricRow}>
                              {reasonMetrics.map((metric) => (
                                <Text key={metric.id} style={styles.stopReasonMetricPill}>
                                  {metric.label} {metric.value}
                                </Text>
                              ))}
                            </View>
                          ) : null}
                          {stopReasoning.reasons.slice(0, 3).map((reason) => (
                            <Text key={reason} style={styles.stopReasonText}>- {reason}</Text>
                          ))}
                          {stopReasoning.cautions?.length ? (
                            <Text style={styles.stopReasonCaution}>
                              Watch: {stopReasoning.cautions.slice(0, 2).join(' ')}
                            </Text>
                          ) : null}
                        </View>
                      ) : null}
                      {stop.diversity_groups?.length ? (
                        <View style={styles.stopGroupRow}>
                          {stop.diversity_groups.map((group) => (
                            <Text key={group} style={[styles.stopGroupPill, { color: routeGroupTone(group), borderColor: routeGroupTone(group) }]}>
                              {routeGroupLabel(group)}
                            </Text>
                          ))}
                        </View>
                      ) : null}
                      {stop.recommendation.member_fit?.length ? (
                        <View style={styles.stopFitRow}>
                          {stop.recommendation.member_fit.map((member) => (
                            <Text key={member.user_id} style={styles.stopFitPill} numberOfLines={1}>
                              {member.display_name} {formatFitPercent(member.fit)}
                            </Text>
                          ))}
                        </View>
                      ) : null}
                      {stopPartySummary?.headline ? (
                        <View style={styles.stopPartySummary}>
                          <Text style={styles.stopPartySummaryTitle}>Party signal</Text>
                          <Text style={styles.stopPartySummaryText}>{stopPartySummary.headline}</Text>
                          {(stopPartySummary.top_members?.length || stopPartySummary.weak_members?.length) ? (
                            <View style={styles.stopPartyChipRow}>
                              {stopPartySummary.top_members?.slice(0, 2).map((member) => (
                                <Text key={`top-${member.user_id}`} style={styles.stopPartyStrongChip} numberOfLines={1}>
                                  Strong for {member.display_name}
                                </Text>
                              ))}
                              {stopPartySummary.weak_members?.slice(0, 2).map((member) => (
                                <Text key={`weak-${member.user_id}`} style={styles.stopPartyWeakChip} numberOfLines={1}>
                                  Watch for {member.display_name}
                                </Text>
                              ))}
                            </View>
                          ) : null}
                        </View>
                      ) : null}
                      {stop.alternatives.length ? (
                        <View style={styles.swapSection}>
                          <Text style={styles.swapLabel}>Swap ideas</Text>
                          {stop.alternatives.slice(0, 2).map((alternative, alternativeIndex) => {
                            const swapDecision = swapDecisionForAlternative(alternative);
                            return (
                              <TouchableOpacity
                                key={`${alternative.place_id}-${alternativeIndex}`}
                                style={[
                                  styles.swapButton,
                                  swapDecision?.should_swap && styles.swapButtonRecommended,
                                ]}
                                onPress={() => swapItineraryStop(dayIndex, index, alternativeIndex)}
                                activeOpacity={0.82}
                              >
                                <View style={styles.swapButtonHeader}>
                                  <View style={styles.swapButtonTitleBlock}>
                                    <Text style={styles.swapButtonText} numberOfLines={1}>
                                      {itineraryPlaceName(alternative)}
                                    </Text>
                                    <Text style={styles.swapButtonMeta} numberOfLines={2}>
                                      {swapDecision?.headline || swapImpactSummary(alternative)}
                                    </Text>
                                  </View>
                                  {typeof swapDecision?.confidence === 'number' ? (
                                    <Text style={[
                                      styles.swapConfidencePill,
                                      swapDecision.should_swap && styles.swapConfidencePillReady,
                                    ]}>
                                      {Math.round(swapDecision.confidence * 100)}%
                                    </Text>
                                  ) : null}
                                </View>
                                {swapDecision?.badges?.length ? (
                                  <View style={styles.swapBadgeRow}>
                                    {swapDecision.badges.slice(0, 4).map((badge, badgeIndex) => (
                                      <Text
                                        key={`${badge.label || 'swap'}-${badge.detail || badgeIndex}`}
                                        style={[
                                          styles.swapDecisionBadge,
                                          badge.tone === 'positive' && styles.swapDecisionBadgePositive,
                                          badge.tone === 'caution' && styles.swapDecisionBadgeCaution,
                                        ]}
                                      >
                                        {badge.label}{badge.detail ? ` ${badge.detail}` : ''}
                                      </Text>
                                    ))}
                                  </View>
                                ) : null}
                                {swapDecision?.best_when ? (
                                  <Text style={styles.swapDecisionText} numberOfLines={2}>
                                    {swapDecision.best_when}
                                  </Text>
                                ) : null}
                                {swapDecision?.tradeoff ? (
                                  <Text style={[
                                    styles.swapTradeoffText,
                                    swapDecision.tradeoff.toLowerCase().includes('tradeoff:') && styles.swapTradeoffTextCaution,
                                  ]} numberOfLines={2}>
                                    {swapDecision.tradeoff}
                                  </Text>
                                ) : null}
                              </TouchableOpacity>
                            );
                          })}
                        </View>
                      ) : null}
                    </View>
                  </View>
                  );
                })}
              </View>
            ))}

            {launchChecklist ? (
              <View style={styles.launchChecklistPanel}>
                <View style={styles.launchChecklistHeader}>
                  <View>
                    <Text style={styles.launchChecklistKicker}>Launch checklist</Text>
                    <Text style={styles.launchChecklistTitle}>{launchChecklist.headline || 'Review before starting.'}</Text>
                  </View>
                  <Text style={[
                    styles.launchChecklistPill,
                    launchChecklist.can_start ? styles.launchChecklistPillReady : styles.launchChecklistPillBlocked,
                  ]}>
                    {launchChecklist.can_start ? 'Startable' : 'Needs route'}
                  </Text>
                </View>
                {launchChecklist.items?.slice(0, 5).map((item) => (
                  <View key={item.id} style={styles.launchChecklistItem}>
                    <Text style={[
                      styles.launchChecklistStatus,
                      item.status === 'ready' && styles.launchChecklistStatusReady,
                      item.status === 'warning' && styles.launchChecklistStatusWarning,
                      item.status === 'action_needed' && styles.launchChecklistStatusAction,
                    ]}>
                      {item.status === 'ready' ? 'Ready' : item.status === 'action_needed' ? 'Action' : item.status === 'optional' ? 'Optional' : 'Review'}
                    </Text>
                    <View style={styles.launchChecklistTextBlock}>
                      <Text style={styles.launchChecklistItemLabel}>{item.label}</Text>
                      {item.detail ? (
                        <Text style={styles.launchChecklistItemDetail}>{item.detail}</Text>
                      ) : null}
                      {item.action ? (
                        <Text style={styles.launchChecklistItemAction}>{item.action}</Text>
                      ) : null}
                    </View>
                  </View>
                ))}
              </View>
            ) : null}

            <TouchableOpacity
              style={[styles.startPlanButton, (journeyLoading || !canStartPlan) && styles.planButtonDisabled]}
              onPress={() => startItineraryAsAdventour()}
              disabled={journeyLoading || !canStartPlan}
              activeOpacity={0.86}
            >
              <Text style={styles.startPlanButtonText}>
                {journeyLoading ? 'Starting route...' : 'Start this route'}
              </Text>
            </TouchableOpacity>

            {itineraryPlan.local_events ? (
              <View
                style={styles.eventPreview}
                onLayout={(event) => setEventSectionOffsetY(event.nativeEvent.layout.y)}
              >
                <View style={styles.eventPreviewHeader}>
                  <View>
                    <Text style={styles.eventPreviewTitle}>Local events</Text>
                    <Text style={styles.eventPreviewSubtitle}>Markets, pop-ups, shows, and community finds.</Text>
                  </View>
                  <TouchableOpacity
                    style={styles.eventAddButton}
                    onPress={() => setEventDraftOpen((current) => !current)}
                    activeOpacity={0.82}
                  >
                    <Text style={styles.eventAddButtonText}>{eventDraftOpen ? 'Close' : 'Add event'}</Text>
                  </TouchableOpacity>
                </View>
                {eventSourceSummary ? (
                  <View style={styles.eventSourceSummary}>
                    <View style={styles.eventSourceSummaryHeader}>
                      <View>
                        <Text style={styles.eventSourceSummaryTitle}>Local signal check</Text>
                        <Text style={styles.eventSourceSummaryText}>
                          {eventSourceSummary.message || 'Source quality will improve as Adventour finds stronger local signals.'}
                        </Text>
                      </View>
                      <Text style={styles.eventSourceSummaryScore}>
                        {eventSourceSummary.trusted_source_count || 0} sourced
                      </Text>
                    </View>
                    <View style={styles.eventSourceSummaryChips}>
                      <Text style={styles.eventSourceSummaryChip}>
                        {eventSourceSummary.reservation_ready_count || 0} reservation-ready
                      </Text>
                      {(eventSourceSummary.badges || []).slice(0, 3).map((badge) => (
                        <Text key={badge.kind} style={styles.eventSourceSummaryChip}>
                          {badge.count} {badge.badge}
                        </Text>
                      ))}
                    </View>
                  </View>
                ) : null}
                {eventSocialSummary ? (
                  <View style={[
                    styles.eventSocialSummary,
                    eventSocialSummary.hasSocialSignal && styles.eventSocialSummaryActive,
                  ]}>
                    <View style={styles.eventSocialSummaryHeader}>
                      <View>
                        <Text style={styles.eventSocialSummaryTitle}>Social pulse</Text>
                        <Text style={styles.eventSocialSummaryText}>
                          {eventSocialSummary.headline}
                        </Text>
                      </View>
                      <Text style={styles.eventSocialSummaryScore}>
                        {typeof eventSocialSummary.score === 'number'
                          ? `${Math.round(eventSocialSummary.score * 100)}%`
                          : `${eventSocialSummary.eventCount} event${eventSocialSummary.eventCount === 1 ? '' : 's'}`}
                      </Text>
                    </View>
                    <View style={styles.eventSocialSummaryChips}>
                      <Text style={[
                        styles.eventSocialSummaryChip,
                        (eventSocialSummary.friendGoing > 0 || eventSocialSummary.friendInterested > 0) && styles.eventSocialSummaryChipActive,
                      ]}>
                        {eventSocialSummary.friendGoing} going / {eventSocialSummary.friendInterested} interested friends
                      </Text>
                      <Text style={styles.eventSocialSummaryChip}>
                        {eventSocialSummary.communityGoing} going / {eventSocialSummary.communityInterested} interested
                      </Text>
                      <Text style={styles.eventSocialSummaryChip}>
                        {eventSocialSummary.reservationReady} reservable
                      </Text>
                      <Text style={[
                        styles.eventSocialSummaryChip,
                        eventSocialSummary.meetupReady && styles.eventSocialSummaryChipActive,
                      ]}>
                        {eventSocialSummary.meetupReady ? 'meetup ready' : eventSocialSummary.status || 'social check'}
                      </Text>
                    </View>
                    {eventSocialSummary.topSocialEvent?.title ? (
                      <Text style={styles.eventSocialSummaryText} numberOfLines={1}>
                        Anchor: {eventSocialSummary.topSocialEvent.title}
                      </Text>
                    ) : null}
                    {eventSocialSummary.checklist?.length ? (
                      <View style={styles.eventMeetupChecklist}>
                        {eventSocialSummary.checklist.slice(0, 4).map((item) => (
                          <Text
                            key={item.id || item.label}
                            style={[
                              styles.eventMeetupChecklistPill,
                              item.status === 'ready' && styles.eventMeetupChecklistPillReady,
                              item.blocking && styles.eventMeetupChecklistPillBlocking,
                            ]}
                            numberOfLines={1}
                          >
                            {item.label}: {item.status === 'ready' ? 'ready' : item.status || 'check'}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                    {eventSocialSummary.nextAction ? (
                      <Text style={styles.eventSocialSummaryAction} numberOfLines={2}>
                        {eventSocialSummary.nextAction}
                      </Text>
                    ) : null}
                  </View>
                ) : null}
                {itineraryPlan.local_events.event_plan ? (
                  <View style={styles.eventPlanBox}>
                    <View style={styles.eventPlanHeader}>
                      <View style={styles.eventPlanTitleGroup}>
                        <Text style={styles.eventPlanTitle}>Event plan</Text>
                        <Text style={styles.eventPlanHeadline} numberOfLines={2}>
                          {itineraryPlan.local_events.event_plan.headline || 'Adventour is checking local event readiness.'}
                        </Text>
                      </View>
                      <Text
                        style={[
                          styles.eventPlanStatus,
                          itineraryPlan.local_events.event_plan.status === 'ready' && styles.eventPlanStatusReady,
                        ]}
                      >
                        {eventPlanStatusLabel(itineraryPlan.local_events.event_plan.status)}
                      </Text>
                    </View>
                    {(itineraryPlan.local_events.event_plan.items || []).slice(0, 4).map((item) => {
                      const actionUrl = item.reservation_url || item.source_url;
                      return (
                        <TouchableOpacity
                          key={`${item.id}-${item.label}`}
                          style={styles.eventPlanItem}
                          onPress={() => actionUrl && Linking.openURL(actionUrl)}
                          disabled={!actionUrl}
                          activeOpacity={0.82}
                        >
                          <View style={styles.eventPlanItemHeader}>
                            <Text style={styles.eventPlanItemLabel}>{item.label}</Text>
                            <Text style={[
                              styles.eventPlanItemPill,
                              item.status === 'ready' && styles.eventPlanItemPillReady,
                              item.status === 'social' && styles.eventPlanItemPillSocial,
                            ]}>
                              {eventPlanItemStatusLabel(item.status)}
                            </Text>
                          </View>
                          {item.detail ? (
                            <Text style={styles.eventPlanItemDetail} numberOfLines={2}>{item.detail}</Text>
                          ) : null}
                          {item.action ? (
                            <Text style={styles.eventPlanItemAction} numberOfLines={2}>
                              {item.action}{actionUrl ? ' Tap to open.' : ''}
                            </Text>
                          ) : null}
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                ) : null}
                {itineraryPlan.local_events.external_sources?.length ? (
                  <View style={styles.eventSourceRow}>
                    {itineraryPlan.local_events.external_sources.map((source) => (
                      <TouchableOpacity
                        key={source.label}
                        style={[
                          styles.eventSourcePill,
                          source.url && styles.eventSourcePillLinked,
                          source.is_recommended && styles.eventSourcePillRecommended,
                        ]}
                        onPress={() => source.url && Linking.openURL(source.url)}
                        disabled={!source.url}
                        activeOpacity={0.82}
                      >
                        <Text style={[styles.eventSourceType, source.is_recommended && styles.eventSourceTypeRecommended]}>
                          {source.is_recommended ? 'Best scout' : eventSourceTypeLabel(source.source_type)}
                        </Text>
                        <Text style={styles.eventSourceLabel}>{source.label}</Text>
                        <Text style={styles.eventSourceDescription} numberOfLines={2}>
                          {source.recommended_reason || source.action || source.description}
                        </Text>
                        {source.reservation_hint ? (
                          <Text style={styles.eventSourceHint} numberOfLines={2}>
                            {source.reservation_hint}
                          </Text>
                        ) : null}
                        {source.url ? (
                          <Text style={styles.eventSourceOpen}>Open source search</Text>
                        ) : null}
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : null}
                {eventDraftOpen ? (
                  <View style={styles.eventForm}>
                    <TextInput
                      style={styles.eventInput}
                      value={eventDraft.title}
                      onChangeText={(value) => setEventDraft((current) => ({ ...current, title: value }))}
                      placeholder="Event title"
                    />
                    <View style={styles.eventInputRow}>
                      <TextInput
                        style={[styles.eventInput, styles.eventInputHalf]}
                        value={eventDraft.starts_at}
                        onChangeText={(value) => setEventDraft((current) => ({ ...current, starts_at: value }))}
                        placeholder="YYYY-MM-DD HH:mm"
                      />
                      <TextInput
                        style={[styles.eventInput, styles.eventInputHalf]}
                        value={eventDraft.category}
                        onChangeText={(value) => setEventDraft((current) => ({ ...current, category: value }))}
                        placeholder="Category"
                      />
                    </View>
                    <TextInput
                      style={[styles.eventInput, styles.eventDescriptionInput]}
                      value={eventDraft.description}
                      onChangeText={(value) => setEventDraft((current) => ({ ...current, description: value }))}
                      placeholder="Why is this worth checking out?"
                      multiline
                    />
                    <View style={styles.eventInputRow}>
                      <TextInput
                        style={[styles.eventInput, styles.eventInputHalf]}
                        value={eventDraft.source_url}
                        onChangeText={(value) => setEventDraft((current) => ({ ...current, source_url: value }))}
                        placeholder="Source link"
                        autoCapitalize="none"
                      />
                      <TextInput
                        style={[styles.eventInput, styles.eventInputHalf]}
                        value={eventDraft.reservation_url}
                        onChangeText={(value) => setEventDraft((current) => ({ ...current, reservation_url: value }))}
                        placeholder="Reserve link"
                        autoCapitalize="none"
                      />
                    </View>
                    <TouchableOpacity
                      style={[styles.eventSubmitButton, eventSaving && styles.planButtonDisabled]}
                      onPress={submitLocalEvent}
                      disabled={eventSaving}
                      activeOpacity={0.86}
                    >
                      <Text style={styles.eventSubmitText}>{eventSaving ? 'Adding...' : 'Add to local events'}</Text>
                    </TouchableOpacity>
                  </View>
                ) : null}
                {itineraryPlan.local_events.events?.length ? (
                  itineraryPlan.local_events.events.map((event) => {
                    const distance = formatEventDistance(event.distance_meters);
                    const routeContext = event.route_context;
                    const routeDistance = formatEventDistance(routeContext?.distance_to_stop_meters ?? undefined);
                    const price = formatEventPrice(event.price_low, event.price_high);
                    const authenticity = typeof event.authenticity_score === 'number'
                      ? `${Math.round(event.authenticity_score * 100)}% local signal`
                      : null;
                    const sourceBadge = event.source?.badge;
                    const sourceDomain = event.source?.domain;
                    const viewerStatus = event.social?.viewer_status;
                    const friendPreview = eventFriendPreviewLabel(event);
                    const eventStory = event.event_story;
                    const readiness = event.event_readiness;
                    const freshnessLabel = localEventFreshnessLabel(event);
                    const freshnessStatus = localEventFreshnessStatus(event);
                    const freshnessAction = localEventFreshnessAction(event);
                    return (
                      <View key={event.id} style={styles.eventCard}>
                        <Text style={styles.eventName}>{event.title}</Text>
                        <Text style={styles.eventMeta}>
                          {formatEventDate(event.starts_at)}{event.category ? ` - ${event.category}` : ''}
                        </Text>
                        {(event.fit_label || routeContext?.fit_label || distance || price || authenticity || sourceBadge || freshnessLabel || readiness) ? (
                          <View style={styles.eventContextRow}>
                            {event.fit_label ? <Text style={styles.eventContextPill}>{event.fit_label}</Text> : null}
                            {routeContext?.fit_label ? <Text style={styles.eventRoutePill}>{routeContext.fit_label}</Text> : null}
                            {distance ? <Text style={styles.eventContextPill}>{distance}</Text> : null}
                            {price ? <Text style={styles.eventContextPill}>{price}</Text> : null}
                            {authenticity ? <Text style={styles.eventContextPill}>{authenticity}</Text> : null}
                            {sourceBadge ? <Text style={styles.eventSourceTrustPill}>{sourceBadge}</Text> : null}
                            {freshnessLabel ? (
                              <Text style={[
                                styles.eventFreshnessPill,
                                freshnessStatus === 'pass' && styles.eventFreshnessPillReady,
                                (freshnessStatus === 'warn' || freshnessStatus === 'watch') && styles.eventFreshnessPillWarn,
                                freshnessStatus === 'fail' && styles.eventFreshnessPillFail,
                              ]}>
                                {freshnessLabel}
                              </Text>
                            ) : null}
                            {readiness ? (
                              <Text style={[
                                styles.eventReadinessPill,
                                readiness.status === 'ready' && styles.eventReadinessPillReady,
                                readiness.status === 'needs_confirmation' && styles.eventReadinessPillConfirm,
                              ]}>
                                {localEventReadinessLabel(readiness.status)}
                              </Text>
                            ) : null}
                          </View>
                        ) : null}
                        {eventStory ? (
                          <View style={[
                            styles.eventStoryBox,
                            eventStory.social_ready && styles.eventStoryBoxSocial,
                          ]}>
                            <View style={styles.eventStoryHeader}>
                              <Text style={styles.eventStoryKicker}>Why this event</Text>
                              {typeof eventStory.confidence === 'number' ? (
                                <Text style={styles.eventStoryScore}>
                                  {Math.round(eventStory.confidence * 100)}%
                                </Text>
                              ) : null}
                            </View>
                            {eventStory.headline ? (
                              <Text style={styles.eventStoryHeadline} numberOfLines={2}>
                                {eventStory.headline}
                              </Text>
                            ) : null}
                            {eventStory.metrics?.length ? (
                              <View style={styles.eventStoryMetricRow}>
                                {eventStory.metrics.slice(0, 4).map((metric) => (
                                  <Text key={metric.id} style={styles.eventStoryMetric}>
                                    {metric.label}{metric.display ? ` ${metric.display}` : ''}
                                  </Text>
                                ))}
                              </View>
                            ) : null}
                            {[...(eventStory.reasons || []), ...(eventStory.cautions || [])].slice(0, 2).map((reason, index) => (
                              <Text
                                key={`${event.id}-event-story-${index}`}
                                style={[
                                  styles.eventStoryReason,
                                  index >= (eventStory.reasons || []).length && styles.eventStoryCaution,
                                ]}
                                numberOfLines={2}
                              >
                                {index >= (eventStory.reasons || []).length ? 'Check: ' : ''}{reason}
                              </Text>
                            ))}
                          </View>
                        ) : null}
                        {readiness ? (
                          <View style={styles.eventReadinessBox}>
                            <View style={styles.eventReadinessHeader}>
                              <Text style={styles.eventReadinessTitle}>
                                {localEventReadinessLabel(readiness.status)}
                              </Text>
                              {typeof readiness.score === 'number' ? (
                                <Text style={styles.eventReadinessScore}>{Math.round(readiness.score * 100)}%</Text>
                              ) : null}
                            </View>
                            {readiness.headline ? (
                              <Text style={styles.eventReadinessText} numberOfLines={2}>
                                {readiness.headline}
                              </Text>
                            ) : null}
                            {readiness.next_action ? (
                              <Text style={styles.eventReadinessAction} numberOfLines={2}>
                                {readiness.next_action}
                              </Text>
                            ) : null}
                            {freshnessAction ? (
                              <Text style={styles.eventReadinessAction} numberOfLines={2}>
                                {freshnessAction}
                              </Text>
                            ) : null}
                          </View>
                        ) : null}
                        {routeContext ? (
                          <Text style={styles.eventRouteContext} numberOfLines={2}>
                            Pairs with {routeContext.stop_name || routeContext.slot_label}
                            {routeContext.time_window ? ` during ${routeContext.time_window}` : ''}
                            {routeDistance ? ` - ${routeDistance} from this stop` : ''}
                          </Text>
                        ) : null}
                        <View style={styles.eventSocialRow}>
                          <Text style={styles.eventSocialPill}>{eventSocialLabel(event)}</Text>
                          {viewerStatus ? (
                            <Text style={styles.eventViewerStatus}>
                              You are {viewerStatus === 'going' ? 'going' : 'interested'}
                            </Text>
                          ) : null}
                        </View>
                        {friendPreview ? (
                          <Text style={styles.eventFriendPreview} numberOfLines={2}>
                            {friendPreview}
                          </Text>
                        ) : null}
                        {event.explanation?.length ? (
                          <Text style={styles.eventFitExplanation} numberOfLines={2}>
                            {event.explanation.slice(0, 3).join(' - ')}
                          </Text>
                        ) : null}
                        {event.description ? (
                          <Text style={styles.eventDescription} numberOfLines={2}>{event.description}</Text>
                        ) : null}
                        <View style={styles.eventInterestRow}>
                          <TouchableOpacity
                            style={[
                              styles.eventInterestButton,
                              viewerStatus === 'interested' && styles.eventInterestButtonSelected,
                            ]}
                            onPress={() => setLocalEventInterest(event, 'interested')}
                            activeOpacity={0.82}
                          >
                            <Text style={[
                              styles.eventInterestText,
                              viewerStatus === 'interested' && styles.eventInterestTextSelected,
                            ]}>
                              Interested
                            </Text>
                          </TouchableOpacity>
                          <TouchableOpacity
                            style={[
                              styles.eventInterestButton,
                              viewerStatus === 'going' && styles.eventInterestButtonSelected,
                            ]}
                            onPress={() => setLocalEventInterest(event, 'going')}
                            activeOpacity={0.82}
                          >
                            <Text style={[
                              styles.eventInterestText,
                              viewerStatus === 'going' && styles.eventInterestTextSelected,
                            ]}>
                              Going
                            </Text>
                          </TouchableOpacity>
                        </View>
                        <View style={styles.eventActionRow}>
                          {event.source_url ? (
                            <TouchableOpacity style={styles.eventLinkButton} onPress={() => Linking.openURL(event.source_url!)}>
                              <Text style={styles.eventLinkText}>{sourceDomain || event.source_name || 'Source'}</Text>
                            </TouchableOpacity>
                          ) : null}
                          {event.reservation_url ? (
                            <TouchableOpacity style={[styles.eventLinkButton, styles.eventReserveButton]} onPress={() => Linking.openURL(event.reservation_url!)}>
                              <Text style={styles.eventReserveText}>Reserve</Text>
                            </TouchableOpacity>
                          ) : null}
                          <TouchableOpacity style={styles.eventSaveButton} onPress={() => openEventReservationDraft(event)}>
                            <Text style={styles.eventSaveText}>Save details</Text>
                          </TouchableOpacity>
                        </View>
                      </View>
                    );
                  })
                ) : (
                  <Text style={styles.eventPreviewText}>{itineraryPlan.local_events.message}</Text>
                )}
              </View>
            ) : null}
          </>
        ) : (
          <Text style={styles.planEmpty}>
            Pick a launch point, choose friends if you want, then let Adventour draft the whole day.
          </Text>
        )}
      </View>
    );
  };

  const renderDestinationScout = () => {
    const currentLaunchIncluded = Boolean(currentCoords && city.trim());
    const candidateCount = destinationLabels().length + (currentLaunchIncluded ? 1 : 0);
    return (
      <View style={styles.destinationScoutPanel}>
        <View style={styles.destinationScoutHeader}>
          <View style={styles.destinationScoutTitleBlock}>
            <Text style={styles.destinationScoutKicker}>Trip scout</Text>
            <Text style={styles.destinationScoutTitle}>Compare destinations before you commit.</Text>
            <Text style={styles.destinationScoutSubtitle}>
              {currentLaunchIncluded
                ? `${city.trim()} is included. Add more cities below.`
                : 'Add cities or neighborhoods, one per line.'}
            </Text>
            {destinationProviderUsageLabel ? (
              <Text style={styles.providerUsageInline}>Live scout: {destinationProviderUsageLabel}</Text>
            ) : null}
          </View>
          <TouchableOpacity
            style={[styles.compareButton, (destinationScoutLoading || candidateCount < 2) && styles.planButtonDisabled]}
            onPress={compareDestinations}
            disabled={destinationScoutLoading || candidateCount < 2}
            activeOpacity={0.86}
          >
            {destinationScoutLoading ? (
              <ActivityIndicator color="#123c69" size="small" />
            ) : (
              <Text style={styles.compareButtonText}>Scout</Text>
            )}
          </TouchableOpacity>
        </View>
        <TextInput
          style={[styles.tripContextInput, styles.destinationScoutInput]}
          value={destinationScoutInput}
          onChangeText={(value) => {
            setDestinationScoutInput(value);
            setDestinationComparisons([]);
            setRecommendedDestinationLabel(null);
            setDestinationProviderUsage(null);
          }}
          placeholder={'Austin, TX\nSavannah, GA\nNew York, NY'}
          multiline
          autoCapitalize="words"
        />
        <Text style={styles.destinationScoutHint}>
          Adventour compares local texture, friend fit, events, swaps, booking readiness, and known per-person costs.
        </Text>
        {destinationComparisons.length ? (
          <View style={styles.destinationScoutList}>
            {destinationComparisons.slice(0, 4).map((comparison) => {
              const destinationLabel = comparison.destination_label || comparison.destination?.label || 'Destination';
              const rank = comparison.destination_rank || comparison.comparison_rank || {};
              const readiness = comparison.route_readiness;
              const isRecommended = destinationLabel === recommendedDestinationLabel || comparison === destinationComparisons[0];
              const price = comparison.known_per_person;
              const headline = comparison.comparison_explanation?.headline;
              const friendTestPacket = comparison.friend_test_packet || comparison.plan?.trip_packet?.friend_test_packet;
              const friendTestStatus = rank.friend_test_status || friendTestPacket?.friend_readiness_status || friendTestPacket?.status;
              const friendTestable = Boolean(rank.friend_testable || friendTestPacket?.friend_testable);
              const friendTestBlockerCount = rank.friend_test_blocker_count ?? (friendTestPacket?.blockers?.length || 0);
              const chips = [
                typeof rank.trip_readiness_score === 'number'
                  ? {
                    key: 'trip',
                    label: 'Trip ready',
                    value: `${Math.round(rank.trip_readiness_score * 100)}%`,
                    tone: rank.trip_readiness_score >= 0.72 ? 'positive' : rank.trip_readiness_score < 0.52 ? 'caution' : 'neutral',
                  }
                  : null,
                typeof rank.authenticity_score === 'number' && rank.authenticity_score > 0
                  ? {
                    key: 'local',
                    label: 'Local',
                    value: `${Math.round(rank.authenticity_score * 100)}%`,
                    tone: rank.authenticity_score >= 0.7 ? 'positive' : 'neutral',
                  }
                  : null,
                typeof rank.event_actionability_score === 'number' && rank.event_actionability_score > 0
                  ? {
                    key: 'events',
                    label: 'Events',
                    value: (rank.event_reservation_ready_count || 0) > 0
                      ? `${rank.event_reservation_ready_count} RSVP`
                      : `${rank.event_actionable_count || rank.event_count || 0}`,
                    tone: (rank.event_reservation_ready_count || 0) > 0 ? 'positive' : 'neutral',
                  }
                  : null,
                typeof rank.booking_handoff_score === 'number' && rank.booking_handoff_score > 0
                  ? {
                    key: 'handoff',
                    label: 'Handoff',
                    value: `${Math.round(rank.booking_handoff_score * 100)}%`,
                    tone: rank.booking_handoff_score >= 0.72 ? 'positive' : 'neutral',
                  }
                  : null,
                selectedFriendIds.length > 0 && (friendTestPacket || rank.friend_test_status || typeof rank.friend_test_score === 'number')
                  ? {
                    key: 'friend-test',
                    label: 'Friend test',
                    value: friendTestable
                      ? 'Ready'
                      : String(friendTestStatus || 'Watch').replace(/_/g, ' '),
                    tone: friendTestable ? 'positive' : friendTestBlockerCount > 0 ? 'caution' : 'neutral',
                  }
                  : null,
                typeof rank.friend_coverage_share === 'number' && selectedFriendIds.length > 0
                  ? {
                    key: 'friends',
                    label: 'Friends',
                    value: `${Math.round(rank.friend_coverage_share * 100)}%`,
                    tone: rank.friend_coverage_share >= 1 ? 'positive' : 'caution',
                  }
                  : null,
                price?.total_known_low !== undefined && price?.total_known_high !== undefined
                  ? {
                    key: 'cost',
                    label: 'Known',
                    value: `$${price.total_known_low}-${price.total_known_high}`,
                    tone: 'neutral',
                  }
                  : null,
              ].filter(Boolean) as { key: string; label: string; value: string; tone: string }[];

              return (
                <View
                  key={`${comparison.destination_id || destinationLabel}-${comparison.scoring_profile}`}
                  style={[styles.destinationScoutRow, isRecommended && styles.destinationScoutRowRecommended]}
                >
                  <View style={styles.destinationScoutRowText}>
                    <Text style={styles.destinationScoutName}>
                      {destinationLabel}{isRecommended ? ' pick' : ''}
                    </Text>
                    <Text style={styles.destinationScoutMeta} numberOfLines={2}>
                      {readiness?.label || 'Route check'} - {Math.round((readiness?.score || 0) * 100)}%
                      {readiness ? ` - ${readiness.planned_stop_count}/${readiness.expected_stop_count} stops` : ''}
                      {comparison.first_stop?.name ? ` - starts at ${comparison.first_stop.name}` : ''}
                    </Text>
                    {headline ? (
                      <Text style={styles.destinationScoutHeadline} numberOfLines={2}>{headline}</Text>
                    ) : null}
                    {chips.length ? (
                      <View style={styles.comparisonSignalRow}>
                        {chips.map((chip) => (
                          <Text
                            key={`${destinationLabel}-${chip.key}`}
                            style={[
                              styles.comparisonSignalPill,
                              chip.tone === 'positive' && styles.comparisonSignalPositive,
                              chip.tone === 'caution' && styles.comparisonSignalCaution,
                            ]}
                          >
                            {chip.label}: {chip.value}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                  </View>
                  <TouchableOpacity
                    style={styles.useComparisonButton}
                    onPress={() => useDestinationComparison(comparison)}
                    activeOpacity={0.84}
                  >
                    <Text style={styles.useComparisonText}>Use trip</Text>
                  </TouchableOpacity>
                </View>
              );
            })}
          </View>
        ) : null}
      </View>
    );
  };

  const renderRecommendationQuality = () => {
    if (!hasLoadedRecommendations || (!recommendationQuality && !basketScenarioReadiness)) {
      return null;
    }

    const quality = recommendationQuality;
    const readiness = basketScenarioReadiness;
    const metrics = quality?.metrics || {};
    const status = quality?.status || readiness?.status;
    const headline = quality?.headline || readiness?.headline;
    const statusLabel = status === 'ready'
      ? 'Friend ready'
      : status === 'needs_attention'
        ? 'Tune'
        : 'Watch';
    const guidance = quality?.warnings?.[0]
      || quality?.next_actions?.[0]
      || quality?.strengths?.[0]
      || readiness?.warnings?.[0]
      || readiness?.next_actions?.[0]
      || readiness?.strengths?.[0];
    const recommendedComparison = basketComparisons.find((comparison) => comparison.scoring_profile === recommendedBasketProfile)
      || basketComparisons[0]
      || null;
    const recommendedStyle = scoutStyleForId(recommendedComparison?.scoring_profile);
    const comparisonExplanation = recommendedComparison?.comparison_explanation;
    const missingIntentCount = metrics.missing_intent_count || 0;
    const partyRescueCount = metrics.party_coverage_rescue_count || 0;
    const firstPageLocalDiscoveryCount = metrics.first_page_local_discovery_count || 0;
    const localDiscoveryRescueCount = metrics.local_discovery_rescue_count || 0;
    const valueGemCount = metrics.value_gem_count || 0;
    const localEventBackedCount = metrics.local_event_backed_count || 0;
    const localEventReservationReadyCount = metrics.local_event_reservation_ready_count || 0;
    const localEventFriendSignalCount = metrics.local_event_friend_signal_count || 0;
    const thinLocalEvidenceCount = metrics.thin_local_evidence_count || 0;
    const authenticityProofPercent = typeof metrics.average_authenticity_confidence === 'number'
      ? Math.round(metrics.average_authenticity_confidence * 100)
      : null;
    const localEventSocialScore = typeof metrics.local_event_social_score === 'number'
      ? Math.round(metrics.local_event_social_score * 100)
      : null;
    const friendHistoryPositiveCount = metrics.friend_history_positive_count || 0;
    const friendHistoryConflictCount = metrics.friend_history_conflict_count || 0;
    const friendCoveragePercent = typeof metrics.member_coverage_share === 'number'
      ? Math.round(metrics.member_coverage_share * 100)
      : null;
    const friendCoveragePlan = selectedFriendIds.length > 0 ? groupFitSummary?.coverage_plan : null;
    const fallbackFriendReadiness: FriendReadinessSummary | null = friendCoveragePlan ? {
        status: friendCoveragePlan.status === 'ready'
          ? 'ready'
          : friendCoveragePlan.status === 'needs_member_coverage'
            ? 'needs_attention'
            : 'watch',
        headline: friendCoveragePlan.headline,
        member_count: groupFitSummary?.member_count,
        covered_member_count: friendCoveragePlan.covered_member_count,
        underserved_count: groupFitSummary?.underserved_members?.length || 0,
        coverage_share: friendCoveragePlan.coverage_share,
        average_group_fit: groupFitSummary?.average_fit,
        members: groupFitSummary?.members,
        underserved_members: groupFitSummary?.underserved_members,
        next_actions: friendCoveragePlan.next_actions,
        watchouts: [],
      } : null;
    const friendReadiness: FriendReadinessSummary | null = selectedFriendIds.length > 0
      ? readiness?.friend_readiness || quality?.friend_readiness || fallbackFriendReadiness
      : null;
    const friendReadinessStatusLabel = friendReadiness?.status === 'ready'
      ? 'Friend ready'
      : friendReadiness?.status === 'needs_attention'
        ? 'Needs match'
        : 'Review';
    const friendReadinessAction = friendReadiness?.next_actions?.[0] || friendReadiness?.watchouts?.[0];
    const friendSuggestionTags = Array.from(new Set(
      (friendReadiness?.underserved_members || [])
        .flatMap((member) => member.suggested_query_tags || [])
        .filter(Boolean)
    )).slice(0, 4);
    const decisionSummary = quality?.decision_summary;
    const decisionAction = decisionSummary?.next_actions?.[0] || decisionSummary?.warnings?.[0];
    const basketTestVerdict = quality?.test_verdict || readiness?.test_verdict;
    const visibleBasketVerdictDimensions = prioritizedTestVerdictDimensions(
      basketTestVerdict?.dimensions,
      selectedFriendIds.length > 0 ? 6 : 5,
    );
    const basketVerdictAction = basketTestVerdict?.next_actions?.[0]
      || basketTestVerdict?.blockers?.[0];
    const modelConfidence = quality?.model_confidence;
    const modelAction = modelConfidence?.warnings?.[0] || modelConfidence?.next_actions?.[0] || modelConfidence?.basis?.[0];
    const modelStatusLabel = modelConfidence?.status === 'ready'
      ? 'Trusted'
      : modelConfidence?.status === 'cold_start'
        ? 'Learning'
        : 'Tuning';
    const learnedBlockedLabel = learnedRerankBlockedLabel(learnedRerankSummary);
    const showLearnedBasketNotice = scoringProfile.learnedRerank && learnedRerankNeedsAttention(learnedRerankSummary);
    const diagnostic = quality?.diagnostic;
    const diagnosticStages = (diagnostic?.stages || [])
      .filter((stage) => stage.status !== 'pass')
      .slice(0, selectedFriendIds.length > 0 ? 5 : 4);
    const visibleDiagnosticStages = diagnosticStages.length
      ? diagnosticStages
      : (diagnostic?.stages || []).slice(0, 4);
    const diagnosticAction = diagnostic?.primary_issue?.next_action
      || diagnostic?.next_actions?.[0];
    const topRemediation = quality?.remediation_plan?.[0] || readiness?.remediation_plan?.[0];
    const topRemediationAction = topRemediation?.actions?.[0];
    const topRemediationAdjustment = remediationAdjustmentLabel(topRemediation?.adjustment);
    const localAuthGuardrailCount = recommendationFilterSummary?.skipped?.local_authenticity_guardrail || 0;
    const serendipityPlan = quality?.serendipity_plan;
    const serendipityAction = serendipityPlan?.next_action || serendipityPlan?.message;
    const serendipityStatusLabel = serendipityPlan?.status === 'balanced'
      ? 'Balanced'
      : serendipityPlan?.status === 'under_target'
        ? 'Conservative'
        : serendipityPlan?.status === 'over_target'
          ? 'Explore-heavy'
          : 'Learning';

    return (
      <View style={styles.basketQualityBox}>
        <View style={styles.basketQualityHeader}>
          <View style={styles.basketQualityTitleBlock}>
            <Text style={styles.basketQualityKicker}>Basket check</Text>
            <Text style={styles.basketQualityHeadline}>
              {headline || 'Adventour checked whether this basket is ready to test.'}
            </Text>
          </View>
          <Text style={[
            styles.basketQualityStatus,
            status === 'ready' && styles.basketQualityStatusReady,
            status === 'needs_attention' && styles.basketQualityStatusAttention,
          ]}>
            {statusLabel}
          </Text>
        </View>
        <View style={styles.basketQualityMetricRow}>
          <Text style={styles.basketQualityMetric}>{metrics.returned || places.length} picks</Text>
          <Text style={styles.basketQualityMetric}>{metrics.hidden_gem_count || 0} gems</Text>
          <Text style={styles.basketQualityMetric}>{Math.round((metrics.local_feeling_share || 0) * 100)}% local</Text>
          {thinLocalEvidenceCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricCaution]}>
              {thinLocalEvidenceCount} thin proof
            </Text>
          ) : authenticityProofPercent !== null ? (
            <Text style={styles.basketQualityMetric}>{authenticityProofPercent}% proof</Text>
          ) : null}
          {typeof metrics.exploration_count === 'number' && metrics.exploration_count > 0 ? (
            <Text style={styles.basketQualityMetric}>
              {metrics.exploration_count} learning
            </Text>
          ) : null}
          {typeof metrics.diversity_coverage === 'number' ? (
            <Text style={styles.basketQualityMetric}>{Math.round(metrics.diversity_coverage * 100)}% variety</Text>
          ) : null}
          {typeof metrics.first_page_diversity_coverage === 'number' ? (
            <Text
              style={[
                styles.basketQualityMetric,
                metrics.first_page_diversity_coverage < 0.67 || (metrics.first_page_dominant_group_share || 0) > 0.7
                  ? styles.basketQualityMetricCaution
                  : null,
              ]}
            >
              {Math.round(metrics.first_page_diversity_coverage * 100)}% opener
            </Text>
          ) : null}
          {firstPageLocalDiscoveryCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {localDiscoveryRescueCount > 0
                ? `${localDiscoveryRescueCount} local rescued`
                : `${firstPageLocalDiscoveryCount} local opener`}
            </Text>
          ) : null}
          {valueGemCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {valueGemCount} value gem{valueGemCount === 1 ? '' : 's'}
            </Text>
          ) : null}
          {typeof metrics.average_group_fit === 'number' ? (
            <Text style={styles.basketQualityMetric}>{Math.round(metrics.average_group_fit * 100)}% party</Text>
          ) : null}
          {partyRescueCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {partyRescueCount} friend rescue{partyRescueCount === 1 ? '' : 's'}
            </Text>
          ) : null}
          {localEventBackedCount > 0 ? (
            <Text style={[styles.basketQualityMetric, localEventReservationReadyCount > 0 ? styles.basketQualityMetricReady : null]}>
              {localEventReservationReadyCount > 0
                ? `${localEventReservationReadyCount} RSVP event${localEventReservationReadyCount === 1 ? '' : 's'}`
                : `${localEventBackedCount} event pick${localEventBackedCount === 1 ? '' : 's'}`}
            </Text>
          ) : null}
          {localEventFriendSignalCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {localEventFriendSignalCount} friend-event signal{localEventFriendSignalCount === 1 ? '' : 's'}
            </Text>
          ) : localEventSocialScore !== null && localEventBackedCount > 0 ? (
            <Text style={styles.basketQualityMetric}>
              {localEventSocialScore}% event signal
            </Text>
          ) : null}
          {friendHistoryPositiveCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {friendHistoryPositiveCount} friend-backed
            </Text>
          ) : null}
          {friendHistoryConflictCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricCaution]}>
              {friendHistoryConflictCount} friend caution{friendHistoryConflictCount === 1 ? '' : 's'}
            </Text>
          ) : null}
          {missingIntentCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricCaution]}>
              {missingIntentCount} mood{missingIntentCount === 1 ? '' : 's'} missing
            </Text>
          ) : null}
          {friendCoveragePercent !== null && selectedFriendIds.length > 0 ? (
            <Text
              style={[
                styles.basketQualityMetric,
                friendCoveragePercent >= 100 ? styles.basketQualityMetricReady : styles.basketQualityMetricCaution,
              ]}
            >
              {friendCoveragePercent}% friend covered
            </Text>
          ) : null}
          {activeFriendBoostLabels.length ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricActive]}>
              Friend-tuned: {activeFriendBoostLabels.join(', ')}
            </Text>
          ) : null}
          {localAuthGuardrailCount > 0 ? (
            <Text style={[styles.basketQualityMetric, styles.basketQualityMetricReady]}>
              {localAuthGuardrailCount} generic filtered
            </Text>
          ) : null}
        </View>
        {serendipityPlan && serendipityPlan.status !== 'empty' ? (
          <View style={[
            styles.discoveryMixBox,
            serendipityPlan.status === 'balanced' && styles.discoveryMixBoxReady,
            ['under_target', 'over_target'].includes(String(serendipityPlan.status || '')) && styles.discoveryMixBoxAttention,
          ]}>
            <View style={styles.discoveryMixHeader}>
              <Text style={styles.discoveryMixKicker}>Discovery mix</Text>
              <Text style={[
                styles.discoveryMixStatus,
                serendipityPlan.status === 'balanced' && styles.discoveryMixStatusReady,
              ]}>
                {serendipityStatusLabel}
              </Text>
            </View>
            <Text style={styles.discoveryMixHeadline} numberOfLines={2}>
              {serendipityPlan.headline || 'Adventour checked safe learning picks.'}
            </Text>
            <View style={styles.discoveryMixMetricRow}>
              <Text style={styles.discoveryMixMetric}>
                {serendipityPlan.allowed_count || 0}/{serendipityPlan.target_max || 0} learning
              </Text>
              <Text style={styles.discoveryMixMetric}>
                {serendipityPlan.safe_count || 0} safe
              </Text>
              {(serendipityPlan.blocked_count || 0) > 0 ? (
                <Text style={[styles.discoveryMixMetric, styles.discoveryMixMetricCaution]}>
                  {serendipityPlan.blocked_count} blocked
                </Text>
              ) : null}
            </View>
            {serendipityAction ? (
              <Text style={[
                styles.discoveryMixText,
                ['under_target', 'over_target'].includes(String(serendipityPlan.status || '')) && styles.discoveryMixTextCaution,
              ]} numberOfLines={2}>
                {serendipityAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {localAuthGuardrailCount > 0 ? (
          <Text style={styles.basketQualityMessage}>
            Adventour kept {localAuthGuardrailCount} chain or generic-risk pick{localAuthGuardrailCount === 1 ? '' : 's'} out because this area had stronger local options.
          </Text>
        ) : null}
        {sessionPulseActive ? (
          <View style={styles.sessionPulseBox}>
            <View style={styles.sessionPulseHeader}>
              <View style={styles.sessionPulseTitleGroup}>
                <Text style={styles.sessionPulseKicker}>Live taste pulse</Text>
                <Text style={styles.sessionPulseTitle}>Reacting to this session</Text>
              </View>
              <Text style={styles.sessionPulseCount}>
                {sessionContext?.signal_count || 0} signal{(sessionContext?.signal_count || 0) === 1 ? '' : 's'}
              </Text>
            </View>
            {sessionPulseSummary ? (
              <Text style={styles.sessionPulseText}>{sessionPulseSummary}</Text>
            ) : null}
            {(sessionPulsePositiveTags.length || sessionPulseNegativeTags.length) ? (
              <View style={styles.sessionPulseTagRow}>
                {sessionPulsePositiveTags.map((label) => (
                  <Text key={`session-positive-${label}`} style={styles.sessionPulseTag}>
                    More {label}
                  </Text>
                ))}
                {sessionPulseNegativeTags.map((label) => (
                  <Text key={`session-negative-${label}`} style={[styles.sessionPulseTag, styles.sessionPulseTagMuted]}>
                    Less {label}
                  </Text>
                ))}
              </View>
            ) : null}
          </View>
        ) : null}
        {topRemediationAction ? (
          <View style={styles.testVerdictBox}>
            <View style={styles.testVerdictHeader}>
              <View style={styles.testVerdictTitleBlock}>
                <Text style={styles.testVerdictKicker}>Next repair</Text>
                <Text style={styles.testVerdictTitle} numberOfLines={2}>
                  {topRemediation?.label || 'Recommended fix'}
                </Text>
              </View>
              <Text style={[
                styles.testVerdictScore,
                topRemediation?.severity === 'needs_attention'
                  ? styles.testVerdictScoreAttention
                  : styles.testVerdictScoreWarning,
              ]}>
                {topRemediation?.severity === 'needs_attention' ? 'Fix' : 'Tune'}
              </Text>
            </View>
            <Text style={[
              styles.testVerdictAction,
              topRemediation?.severity === 'needs_attention' ? styles.basketQualityWarning : null,
            ]} numberOfLines={2}>
              {topRemediationAction}
            </Text>
            {topRemediationAdjustment ? (
              <Text style={styles.testVerdictAction} numberOfLines={1}>
                {topRemediationAdjustment}
              </Text>
            ) : null}
            {topRemediation?.adjustment ? (
              <TouchableOpacity
                style={[styles.repairApplyButton, loading && styles.planButtonDisabled]}
                onPress={() => applyRecommendationRepair(topRemediation.adjustment)}
                disabled={loading}
                activeOpacity={0.84}
              >
                {loading ? (
                  <ActivityIndicator color="#123c69" size="small" />
                ) : (
                  <Text style={styles.repairApplyButtonText}>{remediationButtonLabel(topRemediation.adjustment)}</Text>
                )}
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
        {showLearnedBasketNotice && displayedLearnedRerankStatus ? (
          <View style={styles.learnedBasketNotice}>
            <View style={styles.learnedBasketNoticeHeader}>
              <Text style={styles.learnedBasketNoticeKicker}>Learned beta</Text>
              {learnedBlockedLabel ? (
                <Text style={styles.learnedBasketNoticePill}>{learnedBlockedLabel}</Text>
              ) : null}
            </View>
            <Text style={styles.learnedBasketNoticeText} numberOfLines={3}>
              {displayedLearnedRerankStatus}
            </Text>
            {learnedRerankSummary?.feature_compatibility?.missing_features?.length ? (
              <Text style={styles.learnedBasketNoticeDetail} numberOfLines={1}>
                Missing: {learnedRerankSummary.feature_compatibility.missing_features.slice(0, 3).join(', ')}
                {learnedRerankSummary.feature_compatibility.missing_features.length > 3 ? '...' : ''}
              </Text>
            ) : null}
          </View>
        ) : null}
        {modelConfidence ? (
          <View style={[
            styles.modelConfidenceBox,
            modelConfidence.status === 'ready' && styles.modelConfidenceBoxReady,
            modelConfidence.status === 'cold_start' && styles.modelConfidenceBoxCold,
          ]}>
            <View style={styles.modelConfidenceHeader}>
              <View style={styles.modelConfidenceTitleBlock}>
                <Text style={styles.modelConfidenceKicker}>Model signal</Text>
                <Text style={styles.modelConfidenceTitle} numberOfLines={2}>
                  {modelConfidence.headline || 'Adventour checked how much to trust this recommendation run.'}
                </Text>
              </View>
              {typeof modelConfidence.score === 'number' ? (
                <Text style={[
                  styles.modelConfidenceScore,
                  modelConfidence.status === 'ready' && styles.modelConfidenceScoreReady,
                ]}>
                  {Math.round(modelConfidence.score * 100)}%
                </Text>
              ) : (
                <Text style={[
                  styles.modelConfidenceStatus,
                  modelConfidence.status === 'ready' && styles.modelConfidenceStatusReady,
                ]}>
                  {modelStatusLabel}
                </Text>
              )}
            </View>
            <View style={styles.modelConfidenceMetricRow}>
              <Text style={styles.modelConfidenceMetric}>
                Taste {Math.round((modelConfidence.average_preference_confidence || 0) * 100)}%
              </Text>
              <Text style={styles.modelConfidenceMetric}>
                {Math.round(modelConfidence.average_signal_count || 0)} signals
              </Text>
              <Text style={styles.modelConfidenceMetric}>
                {Math.round((modelConfidence.local_feeling_share || 0) * 100)}% local
              </Text>
              {typeof modelConfidence.member_coverage_share === 'number' && selectedFriendIds.length > 0 ? (
                <Text style={[
                  styles.modelConfidenceMetric,
                  modelConfidence.member_coverage_share >= 1 ? styles.modelConfidenceMetricReady : styles.modelConfidenceMetricCaution,
                ]}>
                  {Math.round(modelConfidence.member_coverage_share * 100)}% friends
                </Text>
              ) : null}
              {(modelConfidence.exploration_count || 0) > 0 ? (
                <Text style={styles.modelConfidenceMetric}>
                  {modelConfidence.exploration_count} learning pick{modelConfidence.exploration_count === 1 ? '' : 's'}
                </Text>
              ) : null}
              {modelConfidence.learned_rerank?.applied ? (
                <Text style={[
                  styles.modelConfidenceMetric,
                  modelConfidence.learned_rerank.guard_status === 'constrained' && styles.modelConfidenceMetricCaution,
                ]}>
                  Learned {modelConfidence.learned_rerank.guard_status || 'active'}
                </Text>
              ) : null}
            </View>
            {modelAction ? (
              <Text style={[
                styles.modelConfidenceAction,
                modelConfidence.warnings?.length ? styles.modelConfidenceActionWarning : null,
              ]} numberOfLines={2}>
            {modelAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {basketTestVerdict ? (
          <View style={styles.testVerdictBox}>
            <View style={styles.testVerdictHeader}>
              <View style={styles.testVerdictTitleBlock}>
                <Text style={styles.testVerdictKicker}>Friend-test verdict</Text>
                <Text style={styles.testVerdictTitle} numberOfLines={2}>
                  {basketTestVerdict.headline || 'Adventour checked whether this basket is ready to share with trusted friends.'}
                </Text>
              </View>
              {typeof basketTestVerdict.score === 'number' ? (
                <Text style={[
                  styles.testVerdictScore,
                  basketTestVerdict.status === 'ready' && styles.testVerdictScoreReady,
                  basketTestVerdict.status === 'needs_attention' && styles.testVerdictScoreAttention,
                ]}>
                  {Math.round(basketTestVerdict.score * 100)}
                </Text>
              ) : null}
            </View>
            {visibleBasketVerdictDimensions.length ? (
              <View style={styles.testVerdictDimensionRow}>
                {visibleBasketVerdictDimensions.map((dimension, index) => (
                  <Text
                    key={`basket-verdict-${dimension.name || dimension.label || 'dimension'}-${index}`}
                    style={[
                      styles.testVerdictDimension,
                      dimension.status === 'pass' && styles.testVerdictDimensionReady,
                      dimension.status === 'fail' && styles.testVerdictDimensionAttention,
                    ]}
                  >
                    {dimension.label || dimension.name || 'Signal'} {typeof dimension.score === 'number' ? `${Math.round(dimension.score * 100)}%` : ''}
                  </Text>
                ))}
              </View>
            ) : null}
            {basketVerdictAction ? (
              <Text style={[
                styles.testVerdictAction,
                basketTestVerdict.blockers?.length ? styles.basketQualityWarning : null,
              ]} numberOfLines={2}>
                {basketVerdictAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {decisionSummary ? (
          <View style={styles.testVerdictBox}>
            <View style={styles.testVerdictHeader}>
              <View style={styles.testVerdictTitleBlock}>
                <Text style={styles.testVerdictKicker}>Run diagnosis</Text>
                <Text style={styles.testVerdictTitle} numberOfLines={2}>
                  {decisionSummary.headline || 'Adventour checked why this basket came back this way.'}
                </Text>
              </View>
              {typeof decisionSummary.score === 'number' ? (
                <Text style={[
                  styles.testVerdictScore,
                  decisionSummary.status === 'ready' && styles.testVerdictScoreReady,
                  decisionSummary.status === 'needs_attention' && styles.testVerdictScoreAttention,
                ]}>
                  {Math.round(decisionSummary.score * 100)}
                </Text>
              ) : null}
            </View>
            {decisionSummary.dimensions?.length ? (
              <View style={styles.testVerdictDimensionRow}>
                {decisionSummary.dimensions.slice(0, selectedFriendIds.length > 0 ? 5 : 4).map((dimension, index) => (
                  <Text
                    key={`${dimension.name || dimension.label || 'dimension'}-${index}`}
                    style={[
                      styles.testVerdictDimension,
                      dimension.status === 'pass' && styles.testVerdictDimensionReady,
                      dimension.status === 'fail' && styles.testVerdictDimensionAttention,
                    ]}
                  >
                    {dimension.label || 'Signal'} {typeof dimension.score === 'number' ? `${Math.round(dimension.score * 100)}%` : ''}
                  </Text>
                ))}
              </View>
            ) : null}
            {decisionAction ? (
              <Text style={[
                styles.testVerdictAction,
                decisionSummary.status === 'needs_attention' ? styles.basketQualityWarning : null,
              ]} numberOfLines={2}>
                {decisionAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {diagnostic ? (
          <View style={styles.testVerdictBox}>
            <View style={styles.testVerdictHeader}>
              <View style={styles.testVerdictTitleBlock}>
                <Text style={styles.testVerdictKicker}>Pipeline read</Text>
                <Text style={styles.testVerdictTitle} numberOfLines={2}>
                  {diagnostic.headline || 'Adventour checked where this recommendation run got stronger or weaker.'}
                </Text>
              </View>
              {diagnostic.primary_issue?.status ? (
                <Text style={[
                  styles.testVerdictScore,
                  diagnostic.primary_issue.status === 'warn' && styles.testVerdictScoreWarning,
                  diagnostic.primary_issue.status === 'fail' && styles.testVerdictScoreAttention,
                  diagnostic.primary_issue.status === 'pass' && styles.testVerdictScoreReady,
                ]}>
                  {diagnostic.primary_issue.status === 'fail' ? 'Fix' : diagnostic.primary_issue.status === 'warn' ? 'Tune' : 'OK'}
                </Text>
              ) : (
                <Text style={[styles.testVerdictScore, styles.testVerdictScoreReady]}>OK</Text>
              )}
            </View>
            {visibleDiagnosticStages.length ? (
              <View style={styles.testVerdictDimensionRow}>
                {visibleDiagnosticStages.map((stage, index) => (
                  <Text
                    key={`pipeline-${stage.name || stage.label || 'stage'}-${index}`}
                    style={[
                      styles.testVerdictDimension,
                      stage.status === 'pass' && styles.testVerdictDimensionReady,
                      stage.status === 'fail' && styles.testVerdictDimensionAttention,
                      stage.status === 'warn' && styles.testVerdictDimensionWarning,
                    ]}
                  >
                    {stage.label || 'Stage'} {typeof stage.score === 'number' ? `${Math.round(stage.score * 100)}%` : ''}
                  </Text>
                ))}
              </View>
            ) : null}
            {diagnostic.primary_issue?.summary ? (
              <Text style={styles.testVerdictAction} numberOfLines={2}>
                {diagnostic.primary_issue.summary}
              </Text>
            ) : null}
            {diagnosticAction ? (
              <Text style={[
                styles.testVerdictAction,
                diagnostic.primary_issue?.status === 'fail' ? styles.basketQualityWarning : null,
              ]} numberOfLines={2}>
                {diagnosticAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {friendReadiness ? (
          <View style={styles.friendReadinessBox}>
            <View style={styles.friendReadinessHeader}>
              <View style={styles.friendReadinessTitleBlock}>
                <Text style={styles.friendReadinessKicker}>Friend readiness</Text>
                <Text style={styles.friendReadinessTitle}>
                  {friendReadiness.headline || 'Adventour checked every traveler in this basket.'}
                </Text>
              </View>
              <Text style={[
                styles.friendReadinessStatus,
                friendReadiness.status === 'ready' && styles.friendReadinessStatusReady,
                friendReadiness.status === 'needs_attention' && styles.friendReadinessStatusAttention,
              ]}>
                {friendReadinessStatusLabel}
              </Text>
            </View>
            <View style={styles.friendReadinessMetricRow}>
              {typeof friendReadiness.coverage_share === 'number' ? (
                <Text style={styles.friendReadinessMetric}>
                  {Math.round(friendReadiness.coverage_share * 100)}% covered
                </Text>
              ) : null}
              {typeof friendReadiness.average_group_fit === 'number' ? (
                <Text style={styles.friendReadinessMetric}>
                  {Math.round(friendReadiness.average_group_fit * 100)}% group fit
                </Text>
              ) : null}
              {typeof friendReadiness.underserved_count === 'number' && friendReadiness.underserved_count > 0 ? (
                <Text style={[styles.friendReadinessMetric, styles.friendReadinessMetricCaution]}>
                  {friendReadiness.underserved_count} needs match
                </Text>
              ) : null}
              {typeof friendReadiness.cold_start_member_count === 'number' && friendReadiness.cold_start_member_count > 0 ? (
                <Text style={[styles.friendReadinessMetric, styles.friendReadinessMetricCaution]}>
                  {friendReadiness.cold_start_member_count} still learning
                </Text>
              ) : null}
            </View>
            {friendReadiness.underserved_members?.length ? (
              <View style={styles.friendReadinessMemberRow}>
                {friendReadiness.underserved_members.slice(0, 2).map((member, index) => (
                  <Text
                    key={`${member.user_id || index}-${member.display_name || 'friend'}-gap`}
                    style={styles.friendReadinessMemberPill}
                    numberOfLines={1}
                  >
                    {member.display_name || 'Traveler'} {typeof member.best_fit === 'number' ? `${Math.round(member.best_fit * 100)}% best` : 'needs a pick'}
                  </Text>
                ))}
              </View>
            ) : null}
            {friendSuggestionTags.length ? (
              <View style={styles.friendReadinessMemberRow}>
                {friendSuggestionTags.map((tag) => (
                  <TouchableOpacity
                    key={`friend-suggestion-${tag}`}
                    activeOpacity={0.8}
                    onPress={() => applyFriendSuggestionTag(tag)}
                    style={[
                      styles.friendReadinessSuggestionChip,
                      boostedFriendQueryTags.includes(tag) ? styles.friendReadinessSuggestionChipActive : null,
                    ]}
                  >
                    <Text
                      style={[
                        styles.friendReadinessSuggestionText,
                        boostedFriendQueryTags.includes(tag) ? styles.friendReadinessSuggestionTextActive : null,
                      ]}
                      numberOfLines={1}
                    >
                      Try {tag.replace(/_/g, ' ')}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
            {friendReadinessAction ? (
              <Text style={styles.friendReadinessAction} numberOfLines={2}>
                {friendReadinessAction}
              </Text>
            ) : null}
          </View>
        ) : null}
        {guidance ? (
          <Text style={[
            styles.basketQualityMessage,
            ((quality?.warnings?.length || readiness?.warnings?.length) || status === 'needs_attention') ? styles.basketQualityWarning : null,
          ]} numberOfLines={3}>
            {guidance}
          </Text>
        ) : null}
        {recommendedComparison && recommendedStyle ? (
          <View style={styles.basketScoutPickBox}>
            <View style={styles.basketScoutPickHeader}>
              <Text style={styles.basketScoutPickKicker}>Auto scout pick</Text>
              <Text style={styles.basketScoutPickName}>{recommendedStyle.label}</Text>
            </View>
            <Text style={styles.basketScoutPickMessage} numberOfLines={2}>
              {comparisonExplanation?.headline || `${recommendedStyle.helper} is the strongest style for this basket.`}
            </Text>
            {basketProviderUsageLabel ? (
              <Text style={styles.providerUsagePill}>
                Live scout: {basketProviderUsageLabel}
              </Text>
            ) : null}
            {comparisonExplanation?.tradeoffs?.length ? (
              <View style={styles.basketScoutTradeoffRow}>
                {comparisonExplanation.tradeoffs.slice(0, 4).map((tradeoff) => (
                  <Text
                    key={`${recommendedComparison.scoring_profile}-${tradeoff.kind}-${tradeoff.label}`}
                    style={[
                      styles.basketScoutTradeoff,
                      tradeoff.tone === 'positive' && styles.basketScoutTradeoffPositive,
                      tradeoff.tone === 'caution' && styles.basketScoutTradeoffCaution,
                    ]}
                  >
                    {tradeoff.label}: {tradeoff.value}
                  </Text>
                ))}
              </View>
            ) : null}
          </View>
        ) : null}
      </View>
    );
  };

  const renderLocalEventPreview = () => {
    if (!hasLoadedRecommendations && !localEventPreview && !localEventsLoading) {
      return null;
    }

    const events = localEventPreview?.events || [];
    const sourceSummary = localEventPreview?.summary?.source_summary;
    const scoutingBrief = sourceSummary?.scouting_brief;
    const firstSource = localEventPreview?.external_sources?.find((source) => source.url);
    const scoutSource = scoutingBrief?.recommended_source?.url
      ? scoutingBrief.recommended_source
      : firstSource;

    return (
      <View
        style={styles.eventPreview}
        onLayout={(event) => setEventSectionOffsetY(event.nativeEvent.layout.y)}
      >
        <View style={styles.eventPreviewHeader}>
          <View>
            <Text style={styles.eventPreviewTitle}>Local events nearby</Text>
            <Text style={styles.eventPreviewSubtitle}>Markets, pop-ups, shows, and social finds around this launch point.</Text>
          </View>
          <TouchableOpacity
            style={styles.eventAddButton}
            onPress={() => setEventDraftOpen((current) => !current)}
            activeOpacity={0.82}
          >
            <Text style={styles.eventAddButtonText}>{eventDraftOpen ? 'Close' : 'Add event'}</Text>
          </TouchableOpacity>
        </View>

        {localEventsLoading ? (
          <View style={styles.eventPreviewLoading}>
            <ActivityIndicator color="#123c69" size="small" />
            <Text style={styles.eventPreviewText}>Scouting local calendars...</Text>
          </View>
        ) : null}

        {sourceSummary ? (
          <View style={styles.eventSourceSummary}>
            <View style={styles.eventSourceSummaryHeader}>
              <View>
                <Text style={styles.eventSourceSummaryTitle}>Local signal check</Text>
                <Text style={styles.eventSourceSummaryText}>
                  {sourceSummary.message || 'Source quality will improve as Adventour finds stronger local signals.'}
                </Text>
              </View>
              <Text style={styles.eventSourceSummaryScore}>
                {sourceSummary.trusted_source_count || 0} sourced
              </Text>
            </View>
            <View style={styles.eventSourceSummaryChips}>
              <Text style={styles.eventSourceSummaryChip}>
                {sourceSummary.reservation_ready_count || 0} reservable
              </Text>
              {(sourceSummary.source_badges || []).slice(0, 2).map((badge) => (
                <Text key={`${badge.kind}-preview`} style={styles.eventSourceSummaryChip}>
                  {badge.count} {badge.badge}
                </Text>
              ))}
            </View>
            {scoutingBrief ? (
              <View style={styles.eventScoutingBrief}>
                <Text style={styles.eventScoutingKicker}>Next scout</Text>
                {scoutingBrief.headline ? (
                  <Text style={styles.eventScoutingTitle}>{scoutingBrief.headline}</Text>
                ) : null}
                {scoutingBrief.detail ? (
                  <Text style={styles.eventScoutingText} numberOfLines={2}>
                    {scoutingBrief.detail}
                  </Text>
                ) : null}
                {scoutingBrief.missing?.length ? (
                  <View style={styles.eventSourceSummaryChips}>
                    {scoutingBrief.missing.slice(0, 3).map((gap) => (
                      <Text
                        key={`${gap.id || gap.label}-scout`}
                        style={[
                          styles.eventSourceSummaryChip,
                          gap.blocking && styles.eventScoutingBlockingChip,
                        ]}
                      >
                        {gap.label}
                      </Text>
                    ))}
                  </View>
                ) : null}
                {scoutSource?.url ? (
                  <TouchableOpacity
                    style={styles.eventScoutingAction}
                    onPress={() => Linking.openURL(scoutSource.url!)}
                    activeOpacity={0.84}
                  >
                    <Text style={styles.eventScoutingActionText}>
                      Open {scoutSource.label || 'recommended'} search
                    </Text>
                  </TouchableOpacity>
                ) : scoutingBrief.next_action ? (
                  <Text style={styles.eventScoutingText} numberOfLines={2}>
                    {scoutingBrief.next_action}
                  </Text>
                ) : null}
              </View>
            ) : null}
          </View>
        ) : null}

        {eventDraftOpen ? (
          <View style={styles.eventForm}>
            <TextInput
              style={styles.eventInput}
              value={eventDraft.title}
              onChangeText={(value) => setEventDraft((current) => ({ ...current, title: value }))}
              placeholder="Event title"
            />
            <View style={styles.eventInputRow}>
              <TextInput
                style={[styles.eventInput, styles.eventInputHalf]}
                value={eventDraft.starts_at}
                onChangeText={(value) => setEventDraft((current) => ({ ...current, starts_at: value }))}
                placeholder="YYYY-MM-DD HH:mm"
              />
              <TextInput
                style={[styles.eventInput, styles.eventInputHalf]}
                value={eventDraft.category}
                onChangeText={(value) => setEventDraft((current) => ({ ...current, category: value }))}
                placeholder="Category"
              />
            </View>
            <TextInput
              style={[styles.eventInput, styles.eventDescriptionInput]}
              value={eventDraft.description}
              onChangeText={(value) => setEventDraft((current) => ({ ...current, description: value }))}
              placeholder="Why is this worth checking out?"
              multiline
            />
            <View style={styles.eventInputRow}>
              <TextInput
                style={[styles.eventInput, styles.eventInputHalf]}
                value={eventDraft.source_url}
                onChangeText={(value) => setEventDraft((current) => ({ ...current, source_url: value }))}
                placeholder="Source link"
                autoCapitalize="none"
              />
              <TextInput
                style={[styles.eventInput, styles.eventInputHalf]}
                value={eventDraft.reservation_url}
                onChangeText={(value) => setEventDraft((current) => ({ ...current, reservation_url: value }))}
                placeholder="Reserve link"
                autoCapitalize="none"
              />
            </View>
            <TouchableOpacity
              style={[styles.eventSubmitButton, eventSaving && styles.planButtonDisabled]}
              onPress={submitLocalEvent}
              disabled={eventSaving}
              activeOpacity={0.86}
            >
              <Text style={styles.eventSubmitText}>{eventSaving ? 'Adding...' : 'Add to local events'}</Text>
            </TouchableOpacity>
          </View>
        ) : null}

        {events.length ? (
          events.slice(0, 2).map((event) => {
            const distance = formatEventDistance(event.distance_meters);
            const sourceBadge = event.source?.badge;
            const sourceDomain = event.source?.domain;
            const viewerStatus = event.social?.viewer_status;
            const eventStory = event.event_story;
            const readiness = event.event_readiness;
            const freshnessLabel = localEventFreshnessLabel(event);
            const freshnessStatus = localEventFreshnessStatus(event);
            const freshnessAction = localEventFreshnessAction(event);
            const friendPreview = eventFriendPreviewLabel(event);
            return (
              <View key={`preview-${event.id}`} style={styles.eventCard}>
                <Text style={styles.eventName}>{event.title}</Text>
                <Text style={styles.eventMeta}>
                  {formatEventDate(event.starts_at)}{event.category ? ` - ${event.category}` : ''}
                </Text>
                <View style={styles.eventContextRow}>
                  {event.fit_label ? <Text style={styles.eventContextPill}>{event.fit_label}</Text> : null}
                  {distance ? <Text style={styles.eventContextPill}>{distance}</Text> : null}
                  {sourceBadge ? <Text style={styles.eventSourceTrustPill}>{sourceBadge}</Text> : null}
                  {freshnessLabel ? (
                    <Text style={[
                      styles.eventFreshnessPill,
                      freshnessStatus === 'pass' && styles.eventFreshnessPillReady,
                      (freshnessStatus === 'warn' || freshnessStatus === 'watch') && styles.eventFreshnessPillWarn,
                      freshnessStatus === 'fail' && styles.eventFreshnessPillFail,
                    ]}>
                      {freshnessLabel}
                    </Text>
                  ) : null}
                  {readiness ? (
                    <Text style={[
                      styles.eventReadinessPill,
                      readiness.status === 'ready' && styles.eventReadinessPillReady,
                      readiness.status === 'needs_confirmation' && styles.eventReadinessPillConfirm,
                    ]}>
                      {localEventReadinessLabel(readiness.status)}
                    </Text>
                  ) : null}
                </View>
                {eventStory?.headline ? (
                  <Text style={styles.eventStoryHeadline} numberOfLines={2}>
                    {eventStory.headline}
                  </Text>
                ) : null}
                {readiness?.next_action ? (
                  <View style={styles.eventReadinessMini}>
                    <Text style={styles.eventReadinessAction} numberOfLines={2}>
                      {readiness.next_action}
                    </Text>
                    {freshnessAction ? (
                      <Text style={styles.eventReadinessAction} numberOfLines={2}>
                        {freshnessAction}
                      </Text>
                    ) : null}
                  </View>
                ) : freshnessAction ? (
                  <View style={styles.eventReadinessMini}>
                    <Text style={styles.eventReadinessAction} numberOfLines={2}>
                      {freshnessAction}
                    </Text>
                  </View>
                ) : null}
                <View style={styles.eventSocialRow}>
                  <Text style={styles.eventSocialPill}>{eventSocialLabel(event)}</Text>
                  {viewerStatus ? (
                    <Text style={styles.eventViewerStatus}>
                      You are {viewerStatus === 'going' ? 'going' : 'interested'}
                    </Text>
                  ) : null}
                </View>
                {friendPreview ? (
                  <Text style={styles.eventFriendPreview} numberOfLines={2}>
                    {friendPreview}
                  </Text>
                ) : null}
                <View style={styles.eventInterestRow}>
                  <TouchableOpacity
                    style={[
                      styles.eventInterestButton,
                      viewerStatus === 'interested' && styles.eventInterestButtonSelected,
                    ]}
                    onPress={() => setLocalEventInterest(event, 'interested')}
                    activeOpacity={0.82}
                  >
                    <Text style={[
                      styles.eventInterestText,
                      viewerStatus === 'interested' && styles.eventInterestTextSelected,
                    ]}>
                      Interested
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[
                      styles.eventInterestButton,
                      viewerStatus === 'going' && styles.eventInterestButtonSelected,
                    ]}
                    onPress={() => setLocalEventInterest(event, 'going')}
                    activeOpacity={0.82}
                  >
                    <Text style={[
                      styles.eventInterestText,
                      viewerStatus === 'going' && styles.eventInterestTextSelected,
                    ]}>
                      Going
                    </Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.eventActionRow}>
                  {event.source_url ? (
                    <TouchableOpacity style={styles.eventLinkButton} onPress={() => Linking.openURL(event.source_url!)}>
                      <Text style={styles.eventLinkText}>{sourceDomain || event.source_name || 'Source'}</Text>
                    </TouchableOpacity>
                  ) : null}
                  {event.reservation_url ? (
                    <TouchableOpacity style={[styles.eventLinkButton, styles.eventReserveButton]} onPress={() => Linking.openURL(event.reservation_url!)}>
                      <Text style={styles.eventReserveText}>Reserve</Text>
                    </TouchableOpacity>
                  ) : null}
                  <TouchableOpacity style={styles.eventSaveButton} onPress={() => openEventReservationDraft(event)}>
                    <Text style={styles.eventSaveText}>Save details</Text>
                  </TouchableOpacity>
                </View>
              </View>
            );
          })
        ) : !localEventsLoading ? (
          <View style={styles.eventPlanItem}>
            <Text style={styles.eventPlanItemLabel}>Scout current events</Text>
            <Text style={styles.eventPlanItemDetail} numberOfLines={2}>
              {localEventPreview?.message || 'No saved local events found nearby yet.'}
            </Text>
            {firstSource?.url ? (
              <TouchableOpacity onPress={() => Linking.openURL(firstSource.url!)} activeOpacity={0.82}>
                <Text style={styles.eventPlanItemAction}>Open {firstSource.label} search.</Text>
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
      </View>
    );
  };

  return (
    <View style={styles.screen}>
      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.greetingBlock}>
          <Text style={styles.greetingText}>{greetingForNow()}, {displayName}</Text>
        </View>
        <View style={styles.discoverModeTabs}>
          <TouchableOpacity
            style={[
              styles.discoverModeTab,
              discoverMode === 'spontaneous' && styles.discoverModeTabActive,
            ]}
            onPress={() => switchDiscoverMode('spontaneous')}
            activeOpacity={0.86}
          >
            <Text style={[
              styles.discoverModeTabText,
              discoverMode === 'spontaneous' && styles.discoverModeTabTextActive,
            ]}>
              Trip by trip
            </Text>
            <Text style={[
              styles.discoverModeTabHelper,
              discoverMode === 'spontaneous' && styles.discoverModeTabHelperActive,
            ]}>
              Swipe places now
            </Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[
              styles.discoverModeTab,
              discoverMode === 'itinerary' && styles.discoverModeTabActive,
            ]}
            onPress={() => switchDiscoverMode('itinerary')}
            activeOpacity={0.86}
          >
            <Text style={[
              styles.discoverModeTabText,
              discoverMode === 'itinerary' && styles.discoverModeTabTextActive,
            ]}>
              Full itinerary
            </Text>
            <Text style={[
              styles.discoverModeTabHelper,
              discoverMode === 'itinerary' && styles.discoverModeTabHelperActive,
            ]}>
              Dates + route
            </Text>
          </TouchableOpacity>
        </View>
        <View style={[styles.launchControls, !hasLaunchPoint && styles.launchControlsRequired]}>
          <View style={styles.launchControlHeader}>
            <Text style={[styles.controlLabel, !hasLaunchPoint && styles.controlLabelRequired]}>
              {discoverMode === 'itinerary'
                ? hasLaunchPoint ? 'Destination' : 'Pick a destination'
                : hasLaunchPoint ? 'Launch point' : 'Pick a launch point'}
            </Text>
            <TouchableOpacity
              style={[
                styles.partyQuickPill,
                selectedFriendIds.length > 0 && styles.partyQuickPillActive,
              ]}
              onPress={() => setFiltersOpen(true)}
              activeOpacity={0.82}
              accessibilityLabel="Open travel party filters"
            >
              <Text
                style={[
                  styles.partyQuickText,
                  selectedFriendIds.length > 0 && styles.partyQuickTextActive,
                ]}
                numberOfLines={1}
              >
                {partySummaryLabel}
              </Text>
            </TouchableOpacity>
          </View>
          <View style={styles.locationContainer}>
            <TextInput
              style={[styles.cityInput, !hasLaunchPoint && styles.cityInputRequired]}
              placeholder={discoverMode === 'itinerary' ? 'Destination city or neighborhood' : 'City, neighborhood, or place'}
              value={city}
              onChangeText={handleCityChange}
              placeholderTextColor="#6b8aa3"
            />
            <TouchableOpacity style={styles.locationButton} onPress={useCurrentLocation}>
              <Image
                source={{ uri: 'https://img.icons8.com/ios-filled/50/ffffff/marker.png' }}
                style={styles.locationIcon}
              />
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.locationButton, styles.filterIconButton, filtersOpen && styles.filterIconButtonActive]}
              onPress={() => setFiltersOpen((open) => !open)}
              activeOpacity={0.82}
              accessibilityLabel="Open filters"
            >
              <View style={styles.filterGlyph}>
                <View style={[styles.filterGlyphLine, styles.filterGlyphLineTop]} />
                <View style={[styles.filterGlyphLine, styles.filterGlyphLineMiddle]} />
                <View style={[styles.filterGlyphLine, styles.filterGlyphLineBottom]} />
              </View>
            </TouchableOpacity>
          </View>
        </View>
        {suggestions.length > 0 && (
          <View style={styles.suggestionsList}>
            {suggestions.map((item) => (
              <TouchableOpacity
                key={item.place_id || item.description}
                style={styles.suggestionItem}
                onPress={() => handleSuggestionSelect(item.description)}
              >
                <Text style={styles.suggestionText}>{item.description}</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}
        {filtersOpen ? (
          <View style={styles.filterSection}>
            <Animated.View style={[styles.filterPanel, filterPanelStyle]}>
              <View style={styles.filterPanelHeader}>
                <View>
                  <Text style={styles.filterTitle}>Filters</Text>
                  <Text style={styles.filterSummary}>
                    {radiusOption.label} - {scoutStyleLabel} - {partySummaryLabel}
                    {excludedTagLabels.length ? ` - skipping ${excludedTagLabels.length}` : ''}
                    {hasLoadedRecommendations ? ` - ${selectedTagLabel}` : ''}
                  </Text>
                </View>
                <TouchableOpacity onPress={() => setFiltersOpen(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                  <Text style={styles.dropdownValue}>Close</Text>
                </TouchableOpacity>
              </View>
              <TouchableOpacity
                style={styles.dropdownButton}
                activeOpacity={0.8}
                onPress={() => setDistanceOpen((open) => !open)}
              >
                <Text style={styles.dropdownLabel}>Search distance</Text>
                <Text style={styles.dropdownValue}>{radiusOption.label} ({radiusOption.helper})</Text>
              </TouchableOpacity>
              {distanceOpen ? (
                <View style={styles.dropdownMenu}>
                  {RADIUS_OPTIONS.map((option) => {
                    const selected = option.id === radiusOption.id;
                    return (
                      <TouchableOpacity
                        key={option.id}
                        style={[styles.dropdownItem, selected && styles.dropdownItemSelected]}
                        onPress={() => {
                          setRadiusOption(option);
                          setDistanceOpen(false);
                        }}
                      >
                        <Text style={[styles.dropdownItemText, selected && styles.dropdownItemTextSelected]}>
                          {option.label}
                        </Text>
                        <Text style={[styles.dropdownHelperText, selected && styles.dropdownItemTextSelected]}>
                          {option.helper}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ) : null}

              <TouchableOpacity
                style={[styles.dropdownButton, !hasLoadedRecommendations && styles.dropdownButtonDisabled]}
                activeOpacity={hasLoadedRecommendations ? 0.8 : 1}
                onPress={() => hasLoadedRecommendations && setTagDropdownOpen((open) => !open)}
              >
                <Text style={styles.dropdownLabel}>Tag group</Text>
                <Text style={styles.dropdownValue}>
                  {hasLoadedRecommendations ? selectedTagLabel : 'Available after search'}
                </Text>
              </TouchableOpacity>
              {hasLoadedRecommendations && tagDropdownOpen ? (
                <View style={styles.dropdownMenu}>
                  <TouchableOpacity
                    style={[styles.dropdownItem, selectedTagGroup === 'all' && styles.dropdownItemSelected]}
                    onPress={() => {
                      setSelectedTagGroup('all');
                      setTagDropdownOpen(false);
                    }}
                  >
                    <Text style={[styles.dropdownItemText, selectedTagGroup === 'all' && styles.dropdownItemTextSelected]}>
                      All picks
                    </Text>
                    <TouchableOpacity onPress={() => showTagDescription('all')} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <Text style={[styles.tagInfo, selectedTagGroup === 'all' && styles.dropdownItemTextSelected]}>?</Text>
                    </TouchableOpacity>
                  </TouchableOpacity>
                  {TAG_GROUPS.map((group) => {
                    const selected = selectedTagGroup === group.id;
                    const count = tagGroupCounts[group.id] || 0;
                    const disabled = count === 0;
                    return (
                      <TouchableOpacity
                        key={group.id}
                        style={[
                          styles.dropdownItem,
                          disabled && styles.dropdownItemDisabled,
                          selected && styles.dropdownItemSelected,
                        ]}
                        activeOpacity={disabled ? 1 : 0.8}
                        onPress={() => {
                          if (disabled) {
                            return;
                          }
                          setSelectedTagGroup(group.id);
                          setTagDropdownOpen(false);
                        }}
                      >
                        <Text
                          style={[
                            styles.dropdownItemText,
                            disabled && styles.dropdownItemTextDisabled,
                            selected && styles.dropdownItemTextSelected,
                          ]}
                        >
                          {group.emoji} {group.label} ({count})
                        </Text>
                        <TouchableOpacity onPress={() => showTagDescription(group.id)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                          <Text style={[styles.tagInfo, selected && styles.dropdownItemTextSelected]}>?</Text>
                        </TouchableOpacity>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              ) : null}
              <View style={styles.scoutStylePanel}>
                <View>
                  <Text style={styles.dropdownLabel}>Scout style</Text>
                  <Text style={styles.scoutStyleSummary}>
                    Use Auto scout to let Adventour compare styles, or pick one to steer the basket yourself.
                  </Text>
                </View>
                <View style={styles.scoutStyleGrid}>
                  {SCORING_PROFILE_OPTIONS.map((option) => {
                    const selected = option.id === scoringProfile.id;
                    return (
                      <TouchableOpacity
                        key={option.id}
                        style={[styles.scoutStyleChip, selected && styles.scoutStyleChipSelected]}
                        activeOpacity={0.84}
                        onPress={() => setScoringProfile(option)}
                      >
                        <Text style={[styles.scoutStyleChipText, selected && styles.scoutStyleChipTextSelected]}>
                          {option.label}
                        </Text>
                        <Text style={[styles.scoutStyleChipHelper, selected && styles.scoutStyleChipHelperSelected]}>
                          {option.helper}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
                {autoScoutLearnedSkipMessage ? (
                  <View style={styles.autoScoutLearnedSkipNotice}>
                    <Text style={styles.autoScoutLearnedSkipKicker}>Auto scout</Text>
                    <Text style={styles.autoScoutLearnedSkipText}>
                      {autoScoutLearnedSkipMessage}
                    </Text>
                  </View>
                ) : null}
                {displayedLearnedRerankStatus ? (
                  <View style={[
                    styles.learnedRerankNotice,
                    learnedRerankSummary?.applied && styles.learnedRerankNoticeActive,
                    learnedRerankSummary?.runtime_guard?.status === 'constrained' && styles.learnedRerankNoticeConstrained,
                  ]}>
                    <View style={styles.learnedRerankNoticeHeader}>
                      <Text style={[
                        styles.learnedRerankNoticeText,
                        styles.learnedRerankNoticeTextWide,
                        learnedRerankSummary?.applied && styles.learnedRerankNoticeTextActive,
                        learnedRerankSummary?.runtime_guard?.status === 'constrained' && styles.learnedRerankNoticeTextConstrained,
                      ]}>
                        {displayedLearnedRerankStatus}
                      </Text>
                      {learnedRankerStatusLoading ? (
                        <ActivityIndicator color="#123c69" size="small" />
                      ) : (
                        <TouchableOpacity
                          style={styles.learnedRerankRefreshButton}
                          onPress={refreshLearnedRankerStatus}
                          activeOpacity={0.84}
                        >
                          <Text style={styles.learnedRerankRefreshText}>Refresh</Text>
                        </TouchableOpacity>
                      )}
                    </View>
                    {learnedRerankSummary?.runtime_guard?.counts ? (
                      <View style={styles.learnedGuardChipRow}>
                        {typeof learnedRerankSummary.runtime_guard.counts.pass === 'number' ? (
                          <Text style={[styles.learnedGuardChip, styles.learnedGuardChipPass]}>
                            {learnedRerankSummary.runtime_guard.counts.pass} safe
                          </Text>
                        ) : null}
                        {typeof learnedRerankSummary.runtime_guard.counts.warn === 'number' && learnedRerankSummary.runtime_guard.counts.warn > 0 ? (
                          <Text style={[styles.learnedGuardChip, styles.learnedGuardChipWatch]}>
                            {learnedRerankSummary.runtime_guard.counts.warn} watch
                          </Text>
                        ) : null}
                        {typeof learnedRerankSummary.runtime_guard.counts.fail === 'number' && learnedRerankSummary.runtime_guard.counts.fail > 0 ? (
                          <Text style={[styles.learnedGuardChip, styles.learnedGuardChipConstrained]}>
                            {learnedRerankSummary.runtime_guard.counts.fail} constrained
                          </Text>
                        ) : null}
                      </View>
                    ) : null}
                    {learnedTrainingHealthChips.length ? (
                      <View style={styles.learnedGuardChipRow}>
                        {learnedTrainingHealthChips.map((chip, index) => (
                          <Text
                            key={`${chip.label}-${index}`}
                            style={[
                              styles.learnedGuardChip,
                              chip.style === 'pass' && styles.learnedGuardChipPass,
                              chip.style === 'watch' && styles.learnedGuardChipWatch,
                              chip.style === 'constrained' && styles.learnedGuardChipConstrained,
                            ]}
                          >
                            {chip.label}
                          </Text>
                        ))}
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
              <View style={styles.tastePanel}>
                <View style={styles.partyHeader}>
                  <View>
                    <Text style={styles.dropdownLabel}>Taste compass</Text>
                    <Text style={styles.tasteSummary}>{tasteStatusMessage(ownPreferenceInsight)}</Text>
                  </View>
                  <View style={styles.tasteStatusPill}>
                    <Text style={styles.tasteStatusText}>{tasteStatusLabel(ownPreferenceInsight?.learning_status)}</Text>
                    <Text style={styles.tasteConfidenceText}>{confidencePercent}%</Text>
                  </View>
                </View>
                {topTasteTags.length || avoidedTasteTags.length ? (
                  <>
                    {topTasteTags.length ? (
                      <View style={styles.tasteChipBlock}>
                        <Text style={styles.tasteChipLabel}>Leaning toward</Text>
                        <View style={styles.tasteChipRow}>
                          {topTasteTags.map((tag) => (
                            <Text key={`like-${tag.tag}`} style={styles.tasteChip}>
                              {tag.label}
                            </Text>
                          ))}
                        </View>
                      </View>
                    ) : null}
                    {avoidedTasteTags.length ? (
                      <View style={styles.tasteChipBlock}>
                        <Text style={styles.tasteChipLabel}>Pulling back from</Text>
                        <View style={styles.tasteChipRow}>
                          {avoidedTasteTags.map((tag) => (
                            <Text key={`avoid-${tag.tag}`} style={[styles.tasteChip, styles.tasteChipAvoid]}>
                              {tag.label}
                            </Text>
                          ))}
                        </View>
                      </View>
                    ) : null}
                  </>
                ) : (
                  <Text style={styles.tasteEmpty}>
                    Swipe on a few places and rate stops to teach Adventour what belongs in your basket.
                  </Text>
                )}
                <View style={styles.tasteMetricRow}>
                  <Text style={styles.tasteMetric}>Signals {ownPreferenceInsight?.signal_count || 0}</Text>
                  <Text style={styles.tasteMetric}>
                    Gems {Math.round((ownPreferenceInsight?.hidden_gem_affinity ?? 0.75) * 100)}%
                  </Text>
                  <Text style={styles.tasteMetric}>
                    Chain guard {Math.round((ownPreferenceInsight?.avoid_chains ?? 0.75) * 100)}%
                  </Text>
                </View>
                {visiblePreferenceInsights.length > 1 ? (
                  <View style={styles.tasteBlendBox}>
                    <Text style={styles.tastePartyNote}>
                      Blending {visiblePreferenceInsights.map((insight) => insight.display_name).join(', ')}.
                    </Text>
                    {visiblePreferenceInsights.map((insight) => {
                      const tags = (insight.top_categories || []).slice(0, 2);
                      return (
                        <View key={insight.user_id} style={styles.tasteBlendRow}>
                          <View style={styles.tasteBlendNameBlock}>
                            <Text style={styles.tasteBlendName} numberOfLines={1}>{insight.display_name}</Text>
                            <Text style={styles.tasteBlendStatus}>
                              {tasteStatusLabel(insight.learning_status)} - {Math.round((insight.confidence || 0) * 100)}%
                            </Text>
                          </View>
                          <View style={styles.tasteBlendTags}>
                            {tags.length ? tags.map((tag) => (
                              <Text key={`${insight.user_id}-${tag.tag}`} style={styles.tasteBlendTag} numberOfLines={1}>
                                {tag.label}
                              </Text>
                            )) : (
                              <Text style={styles.tasteBlendTagMuted}>Needs swipes</Text>
                            )}
                          </View>
                        </View>
                      );
                    })}
                  </View>
                ) : null}
              </View>
              <View style={styles.hardConstraintPanel}>
                <View style={styles.partyHeader}>
                  <View>
                    <Text style={styles.dropdownLabel}>Skip this trip</Text>
                    <Text style={styles.hardConstraintSummary}>
                      Hard excludes for this basket and planned route.
                    </Text>
                  </View>
                  {excludedTagGroups.length ? (
                    <TouchableOpacity
                      onPress={() => {
                        setExcludedTagGroups([]);
                        setItineraryPlan(null);
                      }}
                      hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
                    >
                      <Text style={styles.dropdownValue}>Clear</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
                <View style={styles.hardConstraintGrid}>
                  {TAG_GROUPS.filter((group) => group.id !== 'local_gems').map((group) => {
                    const selected = excludedTagGroups.includes(group.id);
                    return (
                      <TouchableOpacity
                        key={group.id}
                        style={[
                          styles.hardConstraintChip,
                          selected && styles.hardConstraintChipSelected,
                        ]}
                        activeOpacity={0.84}
                        onPress={() => toggleExcludedTagGroup(group.id)}
                      >
                        <Text style={[
                          styles.hardConstraintText,
                          selected && styles.hardConstraintTextSelected,
                        ]}>
                          {selected ? 'Skip ' : ''}{group.emoji} {group.label}
                        </Text>
                      </TouchableOpacity>
                    );
                  })}
                </View>
              </View>
              <View style={styles.partyPanel}>
                <View style={styles.partyHeader}>
                  <View>
                    <Text style={styles.dropdownLabel}>Travel party</Text>
                    <Text style={styles.partySummary}>{partyLabel}</Text>
                  </View>
                  {selectedFriendIds.length > 0 ? (
                    <TouchableOpacity onPress={() => setSelectedFriendIds([])} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                      <Text style={styles.dropdownValue}>Solo</Text>
                    </TouchableOpacity>
                  ) : null}
                </View>
                {friends.length ? (
                  <View style={styles.friendChipRow}>
                    {friends.map((friend) => {
                      const selected = selectedFriendIds.includes(friend.id);
                      return (
                        <TouchableOpacity
                          key={friend.id}
                          style={[styles.friendChip, selected && styles.friendChipSelected]}
                          onPress={() => toggleTravelFriend(friend.id)}
                          activeOpacity={0.82}
                        >
                          <Text style={[styles.friendChipText, selected && styles.friendChipTextSelected]}>
                            {selected ? 'On ' : ''}{friend.display_name || friend.username}
                          </Text>
                        </TouchableOpacity>
                      );
                    })}
                  </View>
                ) : (
                  <Text style={styles.partyEmpty}>Add accepted friends to blend recommendations.</Text>
                )}
                {groupFitSummary && hasLoadedRecommendations ? (
                  <View style={styles.groupFitBox}>
                    <View style={styles.groupFitHeader}>
                      <Text style={styles.groupFitTitle}>Party blend</Text>
                      <Text style={styles.groupFitScore}>
                        {groupFitPercent}% fit{groupFairnessPercent !== null ? ` - ${groupFairnessPercent}% fair` : ''}
                      </Text>
                    </View>
                    {groupFitSummary.message ? (
                      <Text style={styles.groupFitMessage}>{groupFitSummary.message}</Text>
                    ) : null}
                    {groupFitSummary.coverage_plan?.headline ? (
                      <Text style={styles.groupFitMessage}>{groupFitSummary.coverage_plan.headline}</Text>
                    ) : null}
                    {groupFitSummary.members?.length ? (
                      <View style={styles.groupFitMemberRow}>
                        {groupFitSummary.members.slice(0, 4).map((member) => {
                          const underserved = groupFitSummary.underserved_members?.some((item) => item.user_id === member.user_id);
                          const stillLearning = member.learning_status === 'cold_start' || (member.signal_count || 0) < 3;
                          return (
                            <Text
                              key={member.user_id}
                              style={[
                                styles.groupFitMemberPill,
                                underserved && styles.groupFitMemberPillLow,
                                stillLearning && styles.groupFitMemberPillLearning,
                              ]}
                            >
                              {member.display_name} {Math.round(member.average_fit * 100)}%
                              {stillLearning ? ' - Still learning' : ''}
                            </Text>
                          );
                        })}
                      </View>
                    ) : null}
                    {groupFitSummary.coverage_plan?.next_actions?.[0] ? (
                      <Text style={styles.groupFitMessage} numberOfLines={2}>
                        {groupFitSummary.coverage_plan.next_actions[0]}
                      </Text>
                    ) : null}
                    {slateSummary?.member_coverage?.length ? (
                      <View style={styles.partyCoverageList}>
                        {slateSummary.member_coverage.slice(0, 4).map((member) => {
                          const bestMatch = member.best_match;
                          const needsCoverage = member.strong_match_count === 0;
                          return (
                            <View key={`coverage-${member.user_id}`} style={styles.partyCoverageRow}>
                              <Text style={styles.partyCoverageName} numberOfLines={1}>
                                {member.display_name}
                              </Text>
                              <Text
                                style={[
                                  styles.partyCoveragePick,
                                  needsCoverage && styles.partyCoveragePickWeak,
                                ]}
                                numberOfLines={1}
                              >
                                {bestMatch?.name
                                  ? `${needsCoverage ? 'Closest: ' : 'Best: '}${bestMatch.name} (${Math.round((bestMatch.fit || 0) * 100)}%)`
                                  : 'Needs a stronger match'}
                              </Text>
                            </View>
                          );
                        })}
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
            </Animated.View>
          </View>
        ) : null}
        {discoverMode === 'spontaneous' ? (
          <>
            <AdventourLaunchHero
              locationLabel={city || (currentCoords ? 'GPS location' : '')}
              distanceLabel={`${radiusOption.label} range`}
              loading={loading}
              hasResults={hasLoadedRecommendations}
              hasLaunchPoint={hasLaunchPoint}
              activeStopName={activeAdventour?.active_stop?.display?.name}
              onLaunch={handleFindPlaces}
            />
            <AdventourJourneyPanel
              adventour={activeAdventour}
              loading={journeyLoading}
              onStart={handleStartAdventour}
              onOpenDirections={openDirectionsForStop}
              onArrive={handleArriveAtStop}
              onRateStop={handleRateStop}
              onSwapStop={handleSwapActiveStop}
              onEnd={handleEndAdventour}
            />
            <View
              onLayout={(event) => setBasketOffsetY(event.nativeEvent.layout.y)}
            >
              {loading ? (
                <Text style={styles.emptyText}>Loading...</Text>
              ) : hasLoadedRecommendations ? (
                <>
                  {renderRecommendationQuality()}
                  {renderLocalEventPreview()}
                  <RecommendationDeck
                    places={filteredPlaces}
                    activeFilterLabel={selectedTagLabel}
                    partyLabel={partyLabel}
                    totalPlaces={places.length}
                    loadingMore={loadingMore}
                    canLoadMore={autoRefillAvailable}
                    onFeedback={handleFeedback}
                    onOpenPlace={setSelectedPlace}
                    onExhausted={handleRecommendationDeckExhausted}
                  />
                </>
              ) : (
                <Text style={styles.emptyText}>{emptyMessage}</Text>
              )}
            </View>
          </>
        ) : (
          renderItineraryPlan()
        )}
      </ScrollView>
      <PlaceDetailsModal
        place={selectedPlace}
        visible={Boolean(selectedPlace)}
        onClose={() => setSelectedPlace(null)}
      />
    </View>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#bfeaf4',
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: 14,
    paddingTop: 12,
    paddingBottom: 28,
  },
  greetingBlock: {
    marginBottom: 10,
  },
  greetingText: {
    color: '#31506b',
    fontSize: 20,
    fontWeight: '800',
  },
  discoverModeTabs: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 7,
    marginBottom: 10,
    padding: 5,
  },
  discoverModeTab: {
    backgroundColor: '#e8f8fb',
    borderColor: 'transparent',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  discoverModeTabActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  discoverModeTabText: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    textAlign: 'center',
  },
  discoverModeTabTextActive: {
    color: '#fffdf8',
  },
  discoverModeTabHelper: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 2,
    textAlign: 'center',
  },
  discoverModeTabHelperActive: {
    color: '#ffcf7a',
  },
  greetingPrompt: {
    color: '#123c69',
    fontSize: 26,
    fontWeight: '900',
    lineHeight: 30,
    marginTop: 2,
  },
  launchControls: {
    backgroundColor: '#dff6f2',
    borderRadius: 8,
    padding: 10,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#87cfe1',
  },
  controlLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 7,
    textTransform: 'uppercase',
  },
  launchControlHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 7,
  },
  partyQuickPill: {
    alignItems: 'center',
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    maxWidth: '58%',
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  partyQuickPillActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  partyQuickText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
  },
  partyQuickTextActive: {
    color: '#fffaf3',
  },
  launchControlsRequired: {
    borderColor: '#87cfe1',
    backgroundColor: '#e8f8fb',
  },
  controlLabelRequired: {
    color: '#123c69',
    marginBottom: 0,
  },
  input: {
    borderColor: '#eadfce',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    marginBottom: 8,
    backgroundColor: '#fff',
    color: '#1f2937',
  },
  locationContainer: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  cityInput: {
    flex: 1,
    borderColor: '#87cfe1',
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderRadius: 8,
    backgroundColor: '#fff',
    color: '#123c69',
    fontWeight: '700',
  },
  cityInputRequired: {
    borderColor: '#123c69',
    borderWidth: 2,
  },
  locationButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: '#123c69',
    alignItems: 'center',
    justifyContent: 'center',
    marginLeft: 9,
  },
  filterIconButton: {
    backgroundColor: '#ff9f1c',
    borderColor: '#123c69',
    borderWidth: 2,
  },
  filterIconButtonActive: {
    backgroundColor: '#ff4b47',
  },
  filterGlyph: {
    height: 21,
    justifyContent: 'space-between',
    width: 22,
  },
  filterGlyphLine: {
    backgroundColor: '#ffffff',
    borderRadius: 999,
    height: 3,
  },
  filterGlyphLineTop: {
    width: 18,
  },
  filterGlyphLineMiddle: {
    alignSelf: 'flex-end',
    width: 22,
  },
  filterGlyphLineBottom: {
    width: 14,
  },
  locationIcon: {
    width: 24,
    height: 24,
  },
  suggestionsList: {
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    overflow: 'hidden',
    marginBottom: 8,
  },
  suggestionItem: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eadfce',
  },
  suggestionText: {
    color: '#1f2937',
    fontSize: 13,
  },
  tripOriginSuggestionsList: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
    marginTop: -4,
    overflow: 'hidden',
  },
  emptyText: {
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 8,
  },
  basketQualityBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 8,
    padding: 10,
  },
  basketQualityHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 9,
    justifyContent: 'space-between',
  },
  basketQualityTitleBlock: {
    flex: 1,
  },
  basketQualityKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  basketQualityHeadline: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 17,
    marginTop: 2,
  },
  basketQualityStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  basketQualityStatusReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  basketQualityStatusAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  basketQualityMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  basketQualityMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  basketQualityMetricReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  basketQualityMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  basketQualityMetricActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    color: '#fffdf8',
  },
  discoveryMixBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  discoveryMixBoxReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
  },
  discoveryMixBoxAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
  },
  discoveryMixHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  discoveryMixKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  discoveryMixStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  discoveryMixStatusReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  discoveryMixHeadline: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 4,
  },
  discoveryMixMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  discoveryMixMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  discoveryMixMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  discoveryMixText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  discoveryMixTextCaution: {
    color: '#9a3412',
  },
  sessionPulseBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  sessionPulseHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  sessionPulseTitleGroup: {
    flex: 1,
  },
  sessionPulseKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  sessionPulseTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 1,
  },
  sessionPulseCount: {
    backgroundColor: '#dff6f2',
    borderRadius: 999,
    color: '#134e4a',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  sessionPulseText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  sessionPulseTagRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  sessionPulseTag: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  sessionPulseTagMuted: {
    backgroundColor: '#f8fafc',
    borderColor: '#cbd5e1',
    color: '#64748b',
  },
  basketQualityMessage: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 8,
  },
  basketQualityWarning: {
    color: '#9a3412',
  },
  learnedBasketNotice: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  learnedBasketNoticeHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  learnedBasketNoticeKicker: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  learnedBasketNoticePill: {
    backgroundColor: '#fee2e2',
    borderRadius: 999,
    color: '#991b1b',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  learnedBasketNoticeText: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 6,
  },
  learnedBasketNoticeDetail: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 5,
  },
  modelConfidenceBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  modelConfidenceBoxReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#62c7d8',
  },
  modelConfidenceBoxCold: {
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
  },
  modelConfidenceHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  modelConfidenceTitleBlock: {
    flex: 1,
  },
  modelConfidenceKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  modelConfidenceTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  modelConfidenceScore: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  modelConfidenceScoreReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  modelConfidenceStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  modelConfidenceStatusReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  modelConfidenceMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  modelConfidenceMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  modelConfidenceMetricReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#62c7d8',
    color: '#134e4a',
  },
  modelConfidenceMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  modelConfidenceAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  modelConfidenceActionWarning: {
    color: '#9a3412',
  },
  testVerdictBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  testVerdictHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  testVerdictTitleBlock: {
    flex: 1,
  },
  testVerdictKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  testVerdictTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  testVerdictScore: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  testVerdictScoreReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  testVerdictScoreWarning: {
    backgroundColor: '#ffedd5',
    color: '#9a3412',
  },
  testVerdictScoreAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  testVerdictDimensionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 7,
  },
  testVerdictDimension: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  testVerdictDimensionReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    color: '#134e4a',
  },
  testVerdictDimensionWarning: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  testVerdictDimensionAttention: {
    backgroundColor: '#fee2e2',
    borderColor: '#e6534b',
    color: '#991b1b',
  },
  testVerdictAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  repairApplyButton: {
    alignItems: 'center',
    alignSelf: 'flex-start',
    backgroundColor: '#ff9f1c',
    borderColor: '#123c69',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 9,
    minHeight: 32,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  repairApplyButtonText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  friendReadinessBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  friendReadinessHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  friendReadinessTitleBlock: {
    flex: 1,
  },
  friendReadinessKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  friendReadinessTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  friendReadinessStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  friendReadinessStatusReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  friendReadinessStatusAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  friendReadinessMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  friendReadinessMetric: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  friendReadinessMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  friendReadinessSuggestionChip: {
    alignItems: 'center',
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    flexShrink: 1,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  friendReadinessSuggestionChipActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  friendReadinessSuggestionText: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
  },
  friendReadinessSuggestionTextActive: {
    color: '#fffdf8',
  },
  friendReadinessMemberRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  friendReadinessMemberPill: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    color: '#fffdf8',
    flexShrink: 1,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  friendReadinessAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  basketScoutPickBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  basketScoutPickHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  basketScoutPickKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  basketScoutPickName: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    color: '#fffdf8',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  basketScoutPickMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 6,
  },
  providerUsagePill: {
    alignSelf: 'flex-start',
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 7,
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  basketScoutTradeoffRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 7,
  },
  basketScoutTradeoff: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  basketScoutTradeoffPositive: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  basketScoutTradeoffCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  planCard: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    padding: 12,
    shadowColor: '#123c69',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 6,
    elevation: 2,
  },
  planHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 12,
    justifyContent: 'space-between',
  },
  planHeaderText: {
    flex: 1,
  },
  planKicker: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
    letterSpacing: 0.4,
    marginBottom: 3,
    textTransform: 'uppercase',
  },
  planTitle: {
    color: '#123c69',
    fontSize: 19,
    fontWeight: '900',
    lineHeight: 23,
  },
  planSubtitle: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 3,
  },
  planScoutPill: {
    alignSelf: 'flex-start',
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  planScoutLabel: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  planScoutHelper: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 1,
  },
  planButton: {
    alignItems: 'center',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 2,
    justifyContent: 'center',
    minWidth: 78,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  planButtonDisabled: {
    opacity: 0.46,
  },
  planButtonText: {
    color: '#fffdf8',
    fontSize: 13,
    fontWeight: '900',
  },
  magicSetupPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 10,
  },
  magicSetupHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  magicSetupTextBlock: {
    flex: 1,
  },
  magicSetupKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  magicSetupTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 17,
    marginTop: 2,
  },
  magicSetupHint: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 3,
  },
  magicSetupButton: {
    alignItems: 'center',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    flexShrink: 0,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  magicSetupButtonText: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  magicFineTuneButton: {
    alignSelf: 'flex-start',
    marginTop: 9,
  },
  magicFineTuneText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textDecorationLine: 'underline',
  },
  planEmpty: {
    color: '#31506b',
    fontSize: 13,
    fontWeight: '700',
    lineHeight: 19,
    marginTop: 10,
  },
  planDiagnosticPanel: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 10,
  },
  planDiagnosticTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  planDiagnosticText: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 3,
  },
  readinessPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 10,
  },
  readinessHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  readinessTitleBlock: {
    flex: 1,
  },
  readinessKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  readinessTitle: {
    color: '#123c69',
    fontSize: 15,
    fontWeight: '900',
    marginTop: 1,
  },
  readinessStops: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  readinessMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  readinessMetricPill: {
    backgroundColor: 'rgba(255, 253, 248, 0.78)',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  readinessMetricPillReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  readinessPillRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  readinessStrengthPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  readinessWarning: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  authenticityPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 10,
  },
  authenticityPanelReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#62c7d8',
  },
  authenticityPanelAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  authenticityHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  authenticityTitleBlock: {
    flex: 1,
  },
  authenticityKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  authenticityTitle: {
    color: '#123c69',
    fontSize: 14,
    fontWeight: '900',
    lineHeight: 18,
    marginTop: 2,
  },
  authenticityScore: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  authenticityScoreReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  authenticityScoreAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  authenticityMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  authenticityMetric: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  authenticityMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  authenticityMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 8,
  },
  authenticityWarning: {
    color: '#9a3412',
  },
  authenticityStopRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  authenticityStopPill: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    color: '#fffdf8',
    flexShrink: 1,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  itineraryStoryPanel: {
    backgroundColor: '#123c69',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 11,
  },
  itineraryStoryTitle: {
    color: '#fffdf8',
    fontSize: 15,
    fontWeight: '900',
    lineHeight: 20,
  },
  itineraryStoryNarrative: {
    color: '#d7f4fb',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 5,
  },
  itineraryStoryBadgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 10,
  },
  itineraryStoryBadge: {
    backgroundColor: 'rgba(255, 253, 248, 0.12)',
    borderColor: 'rgba(255, 253, 248, 0.28)',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  itineraryStoryBadgeReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
  },
  itineraryStoryBadgeLabel: {
    color: '#ff9f1c',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  itineraryStoryBadgeLabelReady: {
    color: '#0f766e',
  },
  itineraryStoryBadgeDetail: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 1,
    textTransform: 'capitalize',
  },
  itineraryStoryBadgeDetailReady: {
    color: '#123c69',
  },
  itineraryStoryList: {
    gap: 5,
    marginTop: 10,
  },
  itineraryStoryRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 6,
  },
  itineraryStoryDot: {
    color: '#ff9f1c',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 17,
  },
  itineraryStoryText: {
    color: '#fffdf8',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
  },
  itineraryStoryNextBox: {
    backgroundColor: 'rgba(255, 253, 248, 0.12)',
    borderColor: 'rgba(255, 253, 248, 0.22)',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 8,
  },
  itineraryStoryNextTitle: {
    color: '#ff9f1c',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  itineraryStoryNextText: {
    color: '#fffdf8',
    fontSize: 12,
    fontWeight: '800',
    lineHeight: 16,
    marginTop: 3,
  },
  routeExplanationPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 10,
  },
  routeExplanationTitle: {
    color: '#123c69',
    fontSize: 14,
    fontWeight: '900',
  },
  routeExplanationList: {
    gap: 5,
    marginTop: 8,
  },
  routeExplanationRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 6,
  },
  routeExplanationDot: {
    color: '#e6534b',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 17,
  },
  routeExplanationText: {
    color: '#31506b',
    flex: 1,
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
  },
  routeStatsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 9,
  },
  routeStatPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  planModeRow: {
    flexDirection: 'row',
    gap: 7,
    marginTop: 11,
  },
  planModeChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  planModeChipSelected: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  planModeText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    textAlign: 'center',
  },
  planModeTextSelected: {
    color: '#fffdf8',
  },
  planModeHelper: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 2,
    textAlign: 'center',
  },
  planModeHelperSelected: {
    color: '#ffcf7a',
  },
  tripStyleFitBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  tripStyleFitBoxReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
  },
  tripStyleFitBoxAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
  },
  tripStyleFitHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripStyleFitTitleBlock: {
    flex: 1,
  },
  tripStyleFitKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripStyleFitTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripStyleFitScore: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  tripStyleFitScoreReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  tripStyleFitScoreAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  tripStyleFitMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripStyleFitMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripStyleFitMetricReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  tripStyleFitMetricCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  tripStyleFitText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  tripStyleFitTextCaution: {
    color: '#9a3412',
  },
  comparePanel: {
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  compareHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  compareHeaderText: {
    flex: 1,
  },
  compareTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  compareSubtitle: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  providerUsageInline: {
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 5,
  },
  compareButton: {
    alignItems: 'center',
    backgroundColor: '#ff9f1c',
    borderColor: '#123c69',
    borderRadius: 999,
    borderWidth: 1,
    justifyContent: 'center',
    minWidth: 78,
    paddingHorizontal: 11,
    paddingVertical: 8,
  },
  compareButtonText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  comparisonList: {
    gap: 7,
    marginTop: 9,
  },
  comparisonRow: {
    alignItems: 'center',
    backgroundColor: '#fffdf8',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    padding: 8,
  },
  comparisonRowRecommended: {
    borderColor: '#ff9f1c',
    borderWidth: 2,
  },
  comparisonText: {
    flex: 1,
  },
  comparisonName: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  comparisonMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 2,
  },
  comparisonCueRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    marginTop: 5,
  },
  comparisonCuePill: {
    borderRadius: 999,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  comparisonCueReady: {
    backgroundColor: '#d9f99d',
    color: '#365314',
  },
  comparisonCueBlocked: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  comparisonCueText: {
    color: '#4b647c',
    flex: 1,
    fontSize: 10,
    fontWeight: '800',
  },
  comparisonHeadline: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
    marginTop: 5,
  },
  comparisonSignalRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  comparisonSignalPill: {
    backgroundColor: '#eef8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  comparisonSignalPositive: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    color: '#134e4a',
  },
  comparisonSignalCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    color: '#9a3412',
  },
  comparisonTradeoffRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 5,
  },
  comparisonTradeoffPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  comparisonTradeoffPositive: {
    backgroundColor: '#ecfccb',
    borderColor: '#bef264',
    color: '#365314',
  },
  comparisonTradeoffCaution: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  comparisonGroupNote: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 5,
  },
  comparisonGroupNoteCaution: {
    color: '#9a3412',
  },
  useComparisonButton: {
    alignItems: 'center',
    backgroundColor: '#123c69',
    borderRadius: 999,
    minWidth: 76,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  useComparisonText: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  currentComparisonText: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  destinationScoutPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  destinationScoutHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  destinationScoutTitleBlock: {
    flex: 1,
  },
  destinationScoutKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  destinationScoutTitle: {
    color: '#123c69',
    fontSize: 14,
    fontWeight: '900',
    lineHeight: 18,
    marginTop: 2,
  },
  destinationScoutSubtitle: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  destinationScoutInput: {
    minHeight: 82,
    marginBottom: 5,
    marginTop: 9,
    textAlignVertical: 'top',
  },
  destinationScoutHint: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
  },
  destinationScoutList: {
    gap: 7,
    marginTop: 9,
  },
  destinationScoutRow: {
    alignItems: 'center',
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    padding: 8,
  },
  destinationScoutRowRecommended: {
    borderColor: '#ff9f1c',
    borderWidth: 2,
  },
  destinationScoutRowText: {
    flex: 1,
  },
  destinationScoutName: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  destinationScoutMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 2,
  },
  destinationScoutHeadline: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
    marginTop: 5,
  },
  tripContextPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  tripContextTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  tripContextHelp: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginBottom: 8,
    marginTop: 2,
  },
  tripContextInput: {
    backgroundColor: '#fffdf8',
    borderColor: '#b6e2da',
    borderRadius: 8,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 12,
    marginBottom: 8,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  tripDateRow: {
    flexDirection: 'row',
    gap: 8,
  },
  tripDatePickerButton: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  tripDatePickerButtonActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  tripDatePickerLabel: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripDatePickerLabelActive: {
    color: '#ffcf7a',
  },
  tripDatePickerValue: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 2,
  },
  tripDatePickerValueActive: {
    color: '#fffdf8',
  },
  tripDateInput: {
    flex: 1,
    marginBottom: 0,
  },
  tripCalendarPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 9,
  },
  tripCalendarHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  tripCalendarNavButton: {
    alignItems: 'center',
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    height: 32,
    justifyContent: 'center',
    width: 32,
  },
  tripCalendarNavText: {
    color: '#123c69',
    fontSize: 22,
    fontWeight: '900',
    lineHeight: 24,
  },
  tripCalendarTitleBlock: {
    alignItems: 'center',
    flex: 1,
  },
  tripCalendarKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripCalendarTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  tripCalendarWeekRow: {
    flexDirection: 'row',
    marginTop: 10,
  },
  tripCalendarWeekday: {
    color: '#31506b',
    flex: 1,
    fontSize: 10,
    fontWeight: '900',
    textAlign: 'center',
  },
  tripCalendarGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    marginTop: 5,
  },
  tripCalendarDayBlank: {
    aspectRatio: 1,
    width: '14.285%',
  },
  tripCalendarDay: {
    alignItems: 'center',
    aspectRatio: 1,
    justifyContent: 'center',
    width: '14.285%',
  },
  tripCalendarDayToday: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
  },
  tripCalendarDaySelected: {
    backgroundColor: '#123c69',
    borderRadius: 999,
  },
  tripCalendarDayText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  tripCalendarDayTextSelected: {
    color: '#fffdf8',
  },
  tripDateShortcutRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  tripDateShortcutChip: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tripDateClearChip: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
  },
  tripDateShortcutText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  tripDateClearText: {
    color: '#9a3412',
  },
  tripDateError: {
    color: '#9f1239',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 7,
  },
  tripDateReady: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 7,
  },
  tripNeighborhoodInput: {
    marginBottom: 0,
    marginTop: 8,
  },
  tripPreferenceBlock: {
    marginTop: 10,
  },
  tripPreferenceLabel: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  tripPreferenceRow: {
    flexDirection: 'row',
    gap: 7,
  },
  tripPreferenceChip: {
    backgroundColor: '#fffdf8',
    borderColor: '#b6e2da',
    borderRadius: 8,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 7,
    paddingVertical: 7,
  },
  tripPreferenceChipSelected: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  tripPreferenceText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textAlign: 'center',
  },
  tripPreferenceTextSelected: {
    color: '#fffdf8',
  },
  tripPreferenceHelper: {
    color: '#31506b',
    fontSize: 9,
    fontWeight: '800',
    marginTop: 2,
    textAlign: 'center',
  },
  tripPreferenceHelperSelected: {
    color: '#ffcf7a',
  },
  tripPacketPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 10,
  },
  tripPacketPanelReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#62c7d8',
  },
  tripPacketPanelBlocked: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  tripPacketHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  tripPacketTitleBlock: {
    flex: 1,
  },
  tripPacketKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripPacketTitle: {
    color: '#123c69',
    fontSize: 14,
    fontWeight: '900',
    lineHeight: 18,
    marginTop: 2,
  },
  tripPacketScore: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  tripPacketScoreReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketScoreBlocked: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  tripPacketCost: {
    color: '#134e4a',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 7,
  },
  tripPacketCostHint: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 4,
  },
  tripPacketStatRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripPacketStat: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  tripPacketStatReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    color: '#134e4a',
  },
  tripPacketStatManual: {
    backgroundColor: '#fffdf8',
    color: '#31506b',
  },
  tripPacketReservationWallet: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketReservationWalletReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
  },
  tripPacketReservationWalletHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketReservationWalletTitleBlock: {
    flex: 1,
  },
  tripPacketReservationWalletKicker: {
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  tripPacketReservationWalletTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripPacketReservationWalletScore: {
    backgroundColor: '#fffdf8',
    borderColor: '#ffcf7a',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  tripPacketReservationWalletScoreReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketReservationWalletMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  tripPacketReservationWalletMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  tripPacketReservationWalletAction: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 7,
  },
  tripPacketChecklist: {
    backgroundColor: 'rgba(255, 253, 248, 0.82)',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
    marginTop: 9,
    padding: 9,
  },
  tripPacketChecklistHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketChecklistTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripPacketChecklistStatus: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketChecklistStatusReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    color: '#134e4a',
  },
  tripPacketChecklistStatusNeedsDetails: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  tripPacketChecklistRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 7,
  },
  tripPacketChecklistDot: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#123c69',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    minWidth: 22,
    overflow: 'hidden',
    paddingHorizontal: 5,
    paddingVertical: 3,
    textAlign: 'center',
  },
  tripPacketChecklistDotReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  tripPacketChecklistDotAction: {
    backgroundColor: '#ffedd5',
    color: '#9a3412',
  },
  tripPacketChecklistText: {
    color: '#31506b',
    flex: 1,
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
  },
  tripPacketAuthenticity: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketAuthenticityReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#62c7d8',
  },
  tripPacketAuthenticityAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  tripPacketAuthenticityHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketAuthenticityTitleBlock: {
    flex: 1,
  },
  tripPacketAuthenticityKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  tripPacketAuthenticityTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripPacketAuthenticityScore: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketAuthenticityScoreReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketAuthenticityMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripPacketAuthenticityMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketAuthenticityMetricCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  tripPacketAuthenticityMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 6,
  },
  tripPacketFriendTest: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketFriendTestReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#62c7d8',
  },
  tripPacketFriendTestAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  tripPacketFriendTestHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketFriendTestTitleBlock: {
    flex: 1,
  },
  tripPacketFriendTestKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  tripPacketFriendTestTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripPacketFriendTestScore: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketFriendTestScoreReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketFriendTestStatus: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'capitalize',
  },
  tripPacketFriendTestStatusReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketFriendTestMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripPacketFriendTestMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketFriendTestMetricCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  tripPacketFriendTestMetricPositive: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    color: '#134e4a',
  },
  tripPacketFriendTestMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 6,
  },
  tripPacketFriendTestMessageCaution: {
    color: '#9a3412',
  },
  tripPacketFriendTestSwap: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
    marginTop: 7,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  tripPacketEvent: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketEventReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
  },
  tripPacketEventScout: {
    backgroundColor: '#fffdf8',
    borderColor: '#f7d9aa',
  },
  tripPacketEventHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketEventTitleBlock: {
    flex: 1,
  },
  tripPacketEventKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  tripPacketEventTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripPacketEventStatus: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  tripPacketEventStatusReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketEventMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripPacketEventMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketEventTop: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 7,
  },
  tripPacketMeetupAnchor: {
    backgroundColor: 'rgba(255, 253, 248, 0.86)',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  tripPacketMeetupKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.3,
    textTransform: 'uppercase',
  },
  tripPacketMeetupTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 2,
  },
  tripPacketMeetupRoute: {
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 3,
  },
  tripPacketMeetupReason: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 4,
  },
  tripPacketMeetupButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#ff9f1c',
    borderColor: '#123c69',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 7,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  tripPacketMeetupButtonText: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
  },
  tripPacketEventAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 5,
  },
  tripPacketEventSourceButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#123c69',
    borderRadius: 999,
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tripPacketEventSourceText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  tripPacketMobility: {
    backgroundColor: 'rgba(255, 253, 248, 0.82)',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketMobilityHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketMobilityText: {
    flex: 1,
  },
  tripPacketMobilityButtonRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
  },
  tripPacketMobilityKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripPacketMobilityTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 1,
  },
  tripPacketMobilityOpen: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  tripPacketMobilityOpenText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  tripPacketMobilitySave: {
    backgroundColor: '#fffdf8',
    borderColor: '#ff9f1c',
    borderWidth: 1,
  },
  tripPacketMobilitySaveText: {
    color: '#123c69',
  },
  tripPacketMobilityMeta: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 6,
  },
  tripPacketMobilityOption: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 5,
  },
  tripPacketMobilityDistance: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 3,
  },
  tripPacketMobilityStep: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 4,
  },
  tripPacketNext: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 8,
  },
  betaReadinessPanel: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  betaReadinessPanelReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
  },
  betaReadinessPanelBlocked: {
    backgroundColor: '#fff1f2',
    borderColor: '#fda4af',
  },
  betaReadinessHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  betaReadinessTitleBlock: {
    flex: 1,
  },
  betaReadinessKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  betaReadinessTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  betaReadinessScore: {
    backgroundColor: '#fffdf8',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  betaReadinessScoreReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  betaReadinessDimensionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  betaReadinessDimension: {
    backgroundColor: '#fffdf8',
    borderColor: '#f7d9aa',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  betaReadinessDimensionPass: {
    backgroundColor: '#dff6f2',
    borderColor: '#62c7d8',
    color: '#134e4a',
  },
  betaReadinessDimensionFail: {
    backgroundColor: '#ffe4e6',
    borderColor: '#fda4af',
    color: '#9f1239',
  },
  betaReadinessAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  tripPacketCommandCenter: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  tripPacketCommandCenterReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
  },
  tripPacketCommandCenterNeedsDetails: {
    backgroundColor: '#fff1f2',
    borderColor: '#e6534b',
  },
  tripPacketCommandHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  tripPacketCommandTitleBlock: {
    flex: 1,
  },
  tripPacketCommandKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripPacketCommandTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  tripPacketCommandStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 5,
    textTransform: 'capitalize',
  },
  tripPacketCommandStatusReady: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  tripPacketCommandMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  tripPacketCommandMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tripPacketCommandMetricCaution: {
    backgroundColor: '#fee2e2',
    borderColor: '#e6534b',
    color: '#991b1b',
  },
  tripPacketCommandList: {
    gap: 7,
    marginTop: 9,
  },
  tripPacketCommandRow: {
    alignItems: 'center',
    backgroundColor: 'rgba(255, 253, 248, 0.82)',
    borderColor: '#d6edf3',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 7,
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  tripPacketCommandPhase: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  tripPacketCommandPhaseReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  tripPacketCommandPhaseNeeded: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  tripPacketCommandTextBlock: {
    flex: 1,
  },
  tripPacketCommandLabel: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  tripPacketCommandDetail: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 2,
  },
  tripPacketCommandActionRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexShrink: 0,
    gap: 5,
  },
  tripPacketCommandOpen: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    flexShrink: 0,
    paddingHorizontal: 8,
    paddingVertical: 5,
  },
  tripPacketCommandOpenText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  tripPacketCommandSave: {
    backgroundColor: '#fffdf8',
    borderColor: '#123c69',
    borderWidth: 1,
  },
  tripPacketCommandSaveText: {
    color: '#123c69',
  },
  tripPacketActionList: {
    gap: 5,
    marginTop: 8,
  },
  tripPacketActionRow: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 6,
  },
  tripPacketActionDot: {
    color: '#e6534b',
    fontSize: 12,
    fontWeight: '900',
  },
  tripPacketActionText: {
    color: '#9a3412',
    flex: 1,
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
  },
  tripPacketLinkRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  tripPacketLink: {
    backgroundColor: '#123c69',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tripPacketLinkDisabled: {
    opacity: 0.45,
  },
  tripPacketLinkText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  tripPacketSaveRow: {
    gap: 8,
    marginTop: 9,
  },
  tripPacketSavePrompt: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 8,
  },
  tripPacketSavePromptKicker: {
    color: '#f24d4d',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tripPacketSavePromptText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 2,
  },
  priceBand: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 10,
  },
  priceLabel: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  priceValue: {
    color: '#123c69',
    fontSize: 17,
    fontWeight: '900',
    marginTop: 2,
  },
  priceNote: {
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 3,
  },
  savedCostBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  savedCostTitle: {
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  savedCostValue: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 3,
  },
  savedCostCombined: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 3,
  },
  travelerCostList: {
    borderTopColor: '#b6e2da',
    borderTopWidth: 1,
    marginTop: 9,
    paddingTop: 8,
  },
  travelerCostRow: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
    marginBottom: 5,
  },
  travelerCostName: {
    color: '#123c69',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  travelerCostValue: {
    color: '#e6534b',
    fontSize: 12,
    fontWeight: '900',
  },
  travelerCostNote: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 2,
  },
  bookingPanel: {
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  bookingHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 3,
  },
  bookingTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  bookingStatus: {
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingContextText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 4,
  },
  bookingDurationBox: {
    backgroundColor: '#fff8e8',
    borderColor: '#ffb140',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 10,
  },
  bookingDurationBoxNeedsAttention: {
    backgroundColor: '#ffecec',
    borderColor: '#f24d4d',
  },
  bookingDurationKicker: {
    color: '#f24d4d',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  bookingDurationTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 2,
  },
  bookingDurationText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 4,
  },
  bookingDurationAction: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 5,
  },
  bookingChecklistBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  bookingChecklistBoxReady: {
    backgroundColor: '#dff6f2',
  },
  bookingChecklistBoxNeedsDetails: {
    backgroundColor: '#fff3cd',
    borderColor: '#ffcf7a',
  },
  bookingChecklistHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  bookingChecklistTitleBlock: {
    flex: 1,
  },
  bookingChecklistKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  bookingChecklistTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  bookingChecklistStatus: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  bookingChecklistStatusReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  bookingChecklistStatusNeedsDetails: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  bookingChecklistChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  bookingChecklistChip: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexGrow: 1,
    minWidth: '30%',
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  bookingChecklistChipReady: {
    backgroundColor: '#f0fdf4',
    borderColor: '#86efac',
  },
  bookingChecklistChipBlocking: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
  },
  bookingChecklistChipLabel: {
    color: '#31506b',
    fontSize: 8,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingChecklistChipLabelBlocking: {
    color: '#9a3412',
  },
  bookingChecklistChipText: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 2,
  },
  bookingChecklistAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 8,
  },
  bookingHandoffBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  bookingHandoffBoxReady: {
    backgroundColor: '#dff6f2',
  },
  bookingHandoffBoxNeedsDetails: {
    backgroundColor: '#fff3cd',
    borderColor: '#ffcf7a',
  },
  bookingHandoffHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  bookingHandoffTitleBlock: {
    flex: 1,
  },
  bookingHandoffKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  bookingHandoffTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  bookingHandoffStatus: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  bookingHandoffStatusReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  bookingHandoffStatusNeedsDetails: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  bookingHandoffMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  bookingHandoffMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  bookingHandoffNext: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  bookingHandoffChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  bookingHandoffNeedChip: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  bookingHandoffActionRow: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  bookingHandoffAction: {
    backgroundColor: '#123c69',
    borderRadius: 8,
    flex: 1,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  bookingHandoffActionLabel: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  bookingHandoffActionProvider: {
    color: '#dff6f2',
    fontSize: 9,
    fontWeight: '800',
    marginTop: 2,
  },
  bookingHandoffSetup: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 7,
  },
  bookingHandoffSaveButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#ff9f1c',
    borderRadius: 999,
    marginTop: 8,
    paddingHorizontal: 11,
    paddingVertical: 7,
  },
  bookingHandoffSaveText: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
  },
  planningBurdenBox: {
    backgroundColor: '#fff3cd',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  planningBurdenBoxLow: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
  },
  planningBurdenBoxHigh: {
    backgroundColor: '#fee2e2',
    borderColor: '#e6534b',
  },
  planningBurdenHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  planningBurdenTitleBlock: {
    flex: 1,
  },
  planningBurdenKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  planningBurdenTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  planningBurdenPill: {
    backgroundColor: '#ff9f1c',
    borderRadius: 999,
    color: '#123c69',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 4,
  },
  planningBurdenPillLow: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  planningBurdenPillHigh: {
    backgroundColor: '#e6534b',
    color: '#fffdf8',
  },
  planningBurdenAction: {
    color: '#7b4d1b',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
    marginTop: 5,
  },
  planningBurdenChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  planningBurdenChip: {
    backgroundColor: '#fffdf8',
    borderColor: '#f7d9aa',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  bookingMissingText: {
    color: '#9f1239',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 4,
  },
  bookingNextActions: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  bookingNextActionsTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  bookingNextActionText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 2,
  },
  bookingTimelineBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  bookingTimelineHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    marginBottom: 7,
  },
  bookingTimelineKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingTimelineTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 1,
  },
  bookingTimelineStatus: {
    backgroundColor: '#ffedd5',
    borderRadius: 999,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  bookingTimelineStatusReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  bookingTimelineItem: {
    alignItems: 'flex-start',
    borderTopColor: '#d8eef4',
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: 8,
    paddingVertical: 7,
  },
  bookingTimelineStep: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    minWidth: 22,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 4,
    textAlign: 'center',
  },
  bookingTimelineStepReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  bookingTimelineStepAction: {
    backgroundColor: '#ffedd5',
    color: '#9a3412',
  },
  bookingTimelineText: {
    flex: 1,
  },
  bookingTimelineItemHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
  },
  bookingTimelineLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  bookingTimelinePhase: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#31506b',
    fontSize: 8,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 6,
    paddingVertical: 2,
    textTransform: 'uppercase',
  },
  bookingTimelineDetail: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 2,
  },
  bookingTimelineProvider: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 3,
  },
  bookingTimelineOpen: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    paddingTop: 2,
    textTransform: 'uppercase',
  },
  bookingQuickLinks: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  bookingQuickHeader: {
    marginBottom: 7,
  },
  bookingQuickTitle: {
    color: '#ff9f1c',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingQuickSubtitle: {
    color: '#bfeaf4',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 1,
  },
  bookingQuickGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
  },
  bookingQuickCard: {
    backgroundColor: 'rgba(255, 253, 248, 0.12)',
    borderColor: 'rgba(255, 253, 248, 0.24)',
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    padding: 8,
  },
  bookingQuickLabel: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  bookingQuickProvider: {
    color: '#ffcf7a',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 2,
  },
  bookingQuickNote: {
    color: '#dff6f2',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 4,
  },
  bookingQuickActions: {
    flexDirection: 'row',
    gap: 6,
    marginTop: 6,
  },
  bookingQuickButton: {
    alignItems: 'center',
    backgroundColor: '#fffdf8',
    borderRadius: 999,
    flex: 1,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  bookingQuickButtonDisabled: {
    opacity: 0.45,
  },
  bookingQuickSaveButton: {
    backgroundColor: '#ff9f1c',
  },
  bookingQuickButtonText: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingQuickSaveText: {
    color: '#123c69',
  },
  bookingPrepBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  bookingPrepHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  bookingPrepTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  bookingPrepStatus: {
    backgroundColor: '#d9f99d',
    borderRadius: 999,
    color: '#365314',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  bookingPrepStatusAttention: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  bookingPrepHeadline: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 5,
  },
  bookingPrepItem: {
    alignItems: 'flex-start',
    borderTopColor: '#d6edf3',
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: 7,
    marginTop: 7,
    paddingTop: 7,
  },
  bookingPrepItemPill: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#31506b',
    fontSize: 9,
    fontWeight: '900',
    minWidth: 44,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textAlign: 'center',
    textTransform: 'uppercase',
  },
  bookingPrepItemReady: {
    backgroundColor: '#dcfce7',
    color: '#166534',
  },
  bookingPrepItemAction: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  bookingPrepItemManual: {
    backgroundColor: '#ffedd5',
    color: '#9a3412',
  },
  bookingPrepItemText: {
    flex: 1,
  },
  bookingPrepItemLabel: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  bookingPrepItemDetail: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 2,
  },
  bookingPrepProvider: {
    color: '#0f766e',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 2,
  },
  bookingPrepOpen: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    paddingTop: 2,
  },
  bookingItem: {
    backgroundColor: '#fffdf8',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    padding: 8,
  },
  bookingItemHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  bookingLabel: {
    color: '#123c69',
    flex: 1,
    fontSize: 13,
    fontWeight: '900',
  },
  bookingPill: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#31506b',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  bookingPillReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  bookingPillOptional: {
    backgroundColor: '#fff7ed',
    color: '#9a3412',
  },
  bookingEstimate: {
    color: '#e6534b',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 5,
  },
  bookingAction: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 4,
  },
  bookingSearchHint: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  bookingComponentMissing: {
    color: '#9f1239',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 5,
  },
  bookingStepBox: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    padding: 8,
  },
  bookingStepTitle: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  bookingStepText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  bookingProviderRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 7,
  },
  bookingProviderPill: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    padding: 8,
  },
  bookingProviderText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  bookingProviderNote: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 3,
  },
  transportSetupBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    padding: 8,
  },
  transportSetupHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  transportSetupTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  transportSetupLink: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  transportSetupStep: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  transportOptions: {
    marginTop: 8,
  },
  transportDistance: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 6,
  },
  transportOption: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 6,
    padding: 8,
  },
  transportOptionRecommended: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  transportOptionHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  transportOptionLabel: {
    color: '#123c69',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  transportOptionLabelRecommended: {
    color: '#fffdf8',
  },
  transportOptionEstimate: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  transportOptionEstimateRecommended: {
    color: '#ffcf7a',
  },
  transportOptionWhy: {
    color: '#31506b',
    fontSize: 11,
    lineHeight: 15,
    marginTop: 4,
  },
  transportOptionWhyRecommended: {
    color: '#dff6f2',
  },
  transportOptionSetup: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 4,
  },
  transportOptionSetupRecommended: {
    color: '#dff6f2',
  },
  bookingAddButton: {
    alignSelf: 'flex-start',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  bookingAddButtonText: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  reservationForm: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  reservationFormHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  reservationFormTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  reservationCancel: {
    color: '#e6534b',
    fontSize: 12,
    fontWeight: '900',
  },
  reservationInput: {
    backgroundColor: '#ffffff',
    borderColor: '#b6e2da',
    borderRadius: 8,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 12,
    marginBottom: 8,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  reservationInputRow: {
    flexDirection: 'row',
    gap: 8,
  },
  reservationInputHalf: {
    flex: 1,
  },
  reservationNotesInput: {
    minHeight: 58,
    textAlignVertical: 'top',
  },
  reservationSaveButton: {
    alignItems: 'center',
    backgroundColor: '#ff9f1c',
    borderRadius: 8,
    paddingVertical: 9,
  },
  reservationSaveText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  bookingCoverage: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  bookingCoverageHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  bookingCoverageTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  bookingCoverageText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 2,
    maxWidth: 230,
  },
  bookingCoverageStatus: {
    backgroundColor: '#fee2e2',
    borderRadius: 999,
    color: '#991b1b',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  bookingCoverageStatusReady: {
    backgroundColor: '#d8f3dc',
    color: '#166534',
  },
  bookingCoverageChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  bookingCoverageChip: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  bookingCoverageChipSaved: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    color: '#123c69',
  },
  bookingCoverageHint: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 7,
  },
  savedReservations: {
    marginTop: 9,
  },
  savedReservationsTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginBottom: 6,
  },
  savedReservationsSummary: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginBottom: 7,
  },
  savedReservationItem: {
    alignItems: 'center',
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
    marginBottom: 6,
    padding: 8,
  },
  savedReservationText: {
    flex: 1,
  },
  savedReservationTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  savedReservationMeta: {
    color: '#31506b',
    fontSize: 11,
    marginTop: 2,
  },
  savedReservationActions: {
    alignItems: 'flex-end',
    gap: 5,
  },
  savedReservationEdit: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  savedReservationRemove: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  bookingStorageNote: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 8,
  },
  swapGuidePanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 12,
    padding: 10,
  },
  swapGuidePanelReady: {
    backgroundColor: '#e8f8fb',
    borderColor: '#62c7d8',
  },
  swapGuidePanelAttention: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  swapGuideHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  swapGuideTitleBlock: {
    flex: 1,
  },
  swapGuideKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.4,
    textTransform: 'uppercase',
  },
  swapGuideTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 17,
    marginTop: 2,
  },
  swapGuideStatus: {
    backgroundColor: '#ffedd5',
    borderColor: '#fdba74',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'capitalize',
  },
  swapGuideStatusReady: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
    color: '#fffdf8',
  },
  swapGuideMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 9,
  },
  swapGuideMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  swapGuideMetricReady: {
    backgroundColor: '#dff6f2',
    borderColor: '#62c7d8',
    color: '#134e4a',
  },
  swapGuideMetricCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#fdba74',
    color: '#9a3412',
  },
  swapGuideBestBox: {
    backgroundColor: 'rgba(255, 253, 248, 0.78)',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 8,
  },
  swapGuideBestKicker: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  swapGuideBestText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  swapGuideBestReason: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 4,
  },
  swapGuideApplyHint: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 7,
    textTransform: 'uppercase',
  },
  swapGuideAction: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 8,
  },
  planDay: {
    marginTop: 13,
  },
  planDayTitle: {
    color: '#123c69',
    fontSize: 15,
    fontWeight: '900',
  },
  planDaySummary: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    marginBottom: 8,
    marginTop: 2,
  },
  routeMixPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    padding: 8,
  },
  routeMixTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 6,
    textTransform: 'uppercase',
  },
  routeMixChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  routeMixChip: {
    backgroundColor: '#fffdf8',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  routeMixChipText: {
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'capitalize',
  },
  partyFitPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    padding: 9,
  },
  partyFitHeader: {
    marginBottom: 7,
  },
  partyFitTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  partyFitMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  partyFitRows: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  partyFitPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    gap: 3,
    paddingHorizontal: 8,
    paddingVertical: 5,
    width: '48%',
  },
  partyFitPillWeak: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
  },
  partyFitPillTopRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 6,
    justifyContent: 'space-between',
  },
  partyFitName: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    flex: 1,
  },
  partyFitScore: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  partyFitCoverage: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
  },
  partyFitCoverageWeak: {
    color: '#b45309',
  },
  planStop: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 10,
  },
  planStopIndex: {
    alignItems: 'center',
    backgroundColor: '#ff9f1c',
    borderRadius: 999,
    height: 28,
    justifyContent: 'center',
    marginTop: 3,
    width: 28,
  },
  planStopIndexText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  planStopBody: {
    flex: 1,
    backgroundColor: '#fff7ed',
    borderColor: '#f7d9aa',
    borderRadius: 8,
    borderWidth: 1,
    padding: 9,
  },
  planStopWindow: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  planStopLabelRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 2,
  },
  planStopLabel: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '900',
  },
  planStopSwappedPill: {
    backgroundColor: '#dff6f2',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  planStopFriendPill: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#fffdf8',
    flexShrink: 1,
    fontSize: 10,
    fontWeight: '900',
    maxWidth: '100%',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  planStopFriendPillCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
    color: '#e6534b',
  },
  planStopName: {
    color: '#123c69',
    fontSize: 15,
    fontWeight: '900',
    marginTop: 2,
  },
  planStopAddress: {
    color: '#4b5563',
    fontSize: 12,
    marginTop: 2,
  },
  stopEventPanel: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  stopEventHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  stopEventTitleBlock: {
    flex: 1,
  },
  stopEventEyebrow: {
    color: '#e6534b',
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  stopEventTitle: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    marginTop: 2,
  },
  stopEventPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  stopEventPillReady: {
    backgroundColor: '#e6534b',
    borderColor: '#e6534b',
    color: '#fffdf8',
  },
  stopEventMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 5,
  },
  stopEventLink: {
    alignSelf: 'flex-start',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 7,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  stopEventLinkText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
  },
  stopReasonPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  stopReasonTitle: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  stopReasonMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  stopReasonMetricPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  stopReasonText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 3,
  },
  stopReasonCaution: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 5,
  },
  stopGroupRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 7,
  },
  stopGroupPill: {
    borderRadius: 999,
    borderWidth: 1,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'capitalize',
  },
  stopFitRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 8,
  },
  stopFitPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    maxWidth: 126,
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  stopPartySummary: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 8,
  },
  stopPartySummaryTitle: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0,
    textTransform: 'uppercase',
  },
  stopPartySummaryText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  stopPartyChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  stopPartyStrongChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    maxWidth: 144,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  stopPartyWeakChip: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
    borderRadius: 999,
    borderWidth: 1,
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    maxWidth: 144,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  swapSection: {
    marginTop: 8,
  },
  swapLabel: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '900',
    marginBottom: 5,
    textTransform: 'uppercase',
  },
  swapButton: {
    backgroundColor: '#fffdf8',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 5,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  swapButtonRecommended: {
    backgroundColor: '#e8f8fb',
    borderColor: '#123c69',
  },
  swapButtonHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  swapButtonTitleBlock: {
    flex: 1,
  },
  swapButtonText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  swapButtonMeta: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 2,
  },
  swapConfidencePill: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  swapConfidencePillReady: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    color: '#fffdf8',
  },
  swapBadgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  swapDecisionBadge: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'capitalize',
  },
  swapDecisionBadgePositive: {
    backgroundColor: '#dff6f2',
    borderColor: '#0f766e',
    color: '#134e4a',
  },
  swapDecisionBadgeCaution: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
    color: '#9a3412',
  },
  swapDecisionText: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 6,
  },
  swapTradeoffText: {
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
    marginTop: 3,
  },
  swapTradeoffTextCaution: {
    color: '#9a3412',
  },
  launchChecklistPanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 10,
    marginTop: 4,
    padding: 10,
  },
  launchChecklistHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  launchChecklistKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  launchChecklistTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    lineHeight: 17,
    marginTop: 1,
    maxWidth: 225,
  },
  launchChecklistPill: {
    borderRadius: 999,
    borderWidth: 1,
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  launchChecklistPillReady: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    color: '#fffdf8',
  },
  launchChecklistPillBlocked: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
    color: '#e6534b',
  },
  launchChecklistItem: {
    alignItems: 'flex-start',
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexDirection: 'row',
    gap: 8,
    marginTop: 6,
    padding: 8,
  },
  launchChecklistStatus: {
    backgroundColor: '#f3f4f6',
    borderRadius: 999,
    color: '#4b5563',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  launchChecklistStatusReady: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  launchChecklistStatusWarning: {
    backgroundColor: '#fff7ed',
    color: '#9a3412',
  },
  launchChecklistStatusAction: {
    backgroundColor: '#ffe4e6',
    color: '#9f1239',
  },
  launchChecklistTextBlock: {
    flex: 1,
  },
  launchChecklistItemLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  launchChecklistItemDetail: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  launchChecklistItemAction: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 3,
  },
  startPlanButton: {
    alignItems: 'center',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 2,
    marginTop: 4,
    paddingVertical: 12,
  },
  startPlanButtonText: {
    color: '#fffdf8',
    fontSize: 14,
    fontWeight: '900',
  },
  eventPreview: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 4,
    padding: 10,
  },
  eventPreviewTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
  },
  eventPreviewHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  eventPreviewSubtitle: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    marginTop: 2,
  },
  eventPreviewLoading: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    marginTop: 10,
  },
  eventAddButton: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  eventAddButtonText: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  eventSourceSummary: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  eventSourceSummaryHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  eventSourceSummaryTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  eventSourceSummaryText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
    maxWidth: 230,
  },
  eventSourceSummaryScore: {
    color: '#e6534b',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    textAlign: 'right',
  },
  eventSourceSummaryChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  eventSourceSummaryChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventScoutingBrief: {
    backgroundColor: '#e8f8fb',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  eventScoutingKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  eventScoutingTitle: {
    color: '#123c69',
    fontSize: 13,
    fontWeight: '900',
    marginTop: 2,
  },
  eventScoutingText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 3,
  },
  eventScoutingBlockingChip: {
    backgroundColor: '#fff4df',
    borderColor: '#ff9f1c',
    color: '#8a3b00',
  },
  eventScoutingAction: {
    alignSelf: 'flex-start',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  eventScoutingActionText: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '900',
  },
  eventSocialSummary: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  eventSocialSummaryActive: {
    borderColor: '#ff9f1c',
  },
  eventSocialSummaryHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 10,
    justifyContent: 'space-between',
  },
  eventSocialSummaryTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  eventSocialSummaryText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 2,
    maxWidth: 220,
  },
  eventSocialSummaryScore: {
    color: '#e6534b',
    flexShrink: 0,
    fontSize: 11,
    fontWeight: '900',
    textAlign: 'right',
  },
  eventSocialSummaryChips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 8,
  },
  eventSocialSummaryChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventSocialSummaryChipActive: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    color: '#fffdf8',
  },
  eventSocialSummaryAction: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '900',
    lineHeight: 15,
    marginTop: 7,
  },
  eventMeetupChecklist: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  eventMeetupChecklistPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#31506b',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  eventMeetupChecklistPillReady: {
    backgroundColor: '#dff7fa',
    borderColor: '#2fb8c6',
    color: '#123c69',
  },
  eventMeetupChecklistPillBlocking: {
    backgroundColor: '#fff4dc',
    borderColor: '#ff9f1c',
    color: '#7b4d1b',
  },
  eventPlanBox: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  eventPlanHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  eventPlanTitleGroup: {
    flex: 1,
  },
  eventPlanTitle: {
    color: '#ff9f1c',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  eventPlanHeadline: {
    color: '#fffdf8',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
    marginTop: 2,
  },
  eventPlanStatus: {
    backgroundColor: '#e6534b',
    borderRadius: 999,
    color: '#fffdf8',
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'uppercase',
  },
  eventPlanStatusReady: {
    backgroundColor: '#1d9a72',
  },
  eventPlanItem: {
    backgroundColor: 'rgba(255, 253, 248, 0.12)',
    borderColor: 'rgba(255, 253, 248, 0.22)',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    padding: 8,
  },
  eventPlanItemHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  eventPlanItemLabel: {
    color: '#fffdf8',
    flex: 1,
    fontSize: 12,
    fontWeight: '900',
  },
  eventPlanItemPill: {
    backgroundColor: '#e8f8fb',
    borderRadius: 999,
    color: '#123c69',
    flexShrink: 0,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  eventPlanItemPillReady: {
    backgroundColor: '#d8f3dc',
  },
  eventPlanItemPillSocial: {
    backgroundColor: '#ffdda1',
  },
  eventPlanItemDetail: {
    color: '#fffdf8',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 5,
  },
  eventPlanItemAction: {
    color: '#bfeaf4',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 3,
  },
  eventSourceRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  eventSourcePill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  eventSourcePillLinked: {
    borderColor: '#ff9f1c',
  },
  eventSourcePillRecommended: {
    backgroundColor: '#fff4dc',
    borderColor: '#ff9f1c',
    borderWidth: 2,
  },
  eventSourceType: {
    alignSelf: 'flex-start',
    backgroundColor: '#dff7fa',
    borderRadius: 999,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    marginBottom: 4,
    paddingHorizontal: 7,
    paddingVertical: 2,
  },
  eventSourceTypeRecommended: {
    backgroundColor: '#123c69',
    color: '#fffdf8',
  },
  eventSourceLabel: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  eventSourceDescription: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '700',
    lineHeight: 14,
    marginTop: 2,
  },
  eventSourceHint: {
    color: '#7b4d1b',
    fontSize: 9,
    fontWeight: '800',
    lineHeight: 13,
    marginTop: 4,
  },
  eventSourceOpen: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 5,
  },
  eventForm: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 9,
  },
  eventInput: {
    backgroundColor: '#ffffff',
    borderColor: '#b6e2da',
    borderRadius: 8,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 12,
    marginBottom: 8,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  eventInputRow: {
    flexDirection: 'row',
    gap: 8,
  },
  eventInputHalf: {
    flex: 1,
  },
  eventDescriptionInput: {
    minHeight: 58,
    textAlignVertical: 'top',
  },
  eventSubmitButton: {
    alignItems: 'center',
    backgroundColor: '#ff9f1c',
    borderRadius: 8,
    paddingVertical: 9,
  },
  eventSubmitText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  eventPreviewText: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    lineHeight: 17,
    marginTop: 3,
  },
  eventCard: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 9,
  },
  eventName: {
    color: '#123c69',
    fontSize: 14,
    fontWeight: '900',
  },
  eventMeta: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
    marginTop: 2,
  },
  eventContextRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  eventContextPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventRoutePill: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventSourceTrustPill: {
    backgroundColor: '#dff6f2',
    borderColor: '#0f766e',
    borderRadius: 999,
    borderWidth: 1,
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventReadinessPill: {
    backgroundColor: '#fee2e2',
    borderColor: '#e6534b',
    borderRadius: 999,
    borderWidth: 1,
    color: '#7f1d1d',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
    textTransform: 'capitalize',
  },
  eventReadinessPillReady: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    color: '#fffdf8',
  },
  eventReadinessPillConfirm: {
    backgroundColor: '#fff3cd',
    borderColor: '#ff9f1c',
    color: '#7b4d1b',
  },
  eventFreshnessPill: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventFreshnessPillReady: {
    backgroundColor: '#dff8ef',
    borderColor: '#5bc8a8',
    color: '#134e4a',
  },
  eventFreshnessPillWarn: {
    backgroundColor: '#fff7e8',
    borderColor: '#ff9f1c',
    color: '#7b4d1b',
  },
  eventFreshnessPillFail: {
    backgroundColor: '#fee2e2',
    borderColor: '#e6534b',
    color: '#7f1d1d',
  },
  eventReadinessBox: {
    backgroundColor: '#fff7e8',
    borderColor: '#ff9f1c',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 9,
  },
  eventReadinessMini: {
    backgroundColor: '#fff7e8',
    borderColor: '#ffdda1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 7,
    paddingHorizontal: 8,
    paddingVertical: 6,
  },
  eventReadinessHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  eventReadinessTitle: {
    color: '#123c69',
    flex: 1,
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  eventReadinessScore: {
    color: '#e6534b',
    fontSize: 11,
    fontWeight: '900',
  },
  eventReadinessText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 4,
  },
  eventReadinessAction: {
    color: '#7b4d1b',
    fontSize: 10,
    fontWeight: '900',
    lineHeight: 14,
  },
  eventStoryBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 8,
    padding: 9,
  },
  eventStoryBoxSocial: {
    backgroundColor: '#f3e8ff',
    borderColor: '#c4b5fd',
  },
  eventStoryHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  eventStoryKicker: {
    color: '#e6534b',
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.5,
    textTransform: 'uppercase',
  },
  eventStoryScore: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  eventStoryHeadline: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
    lineHeight: 16,
  },
  eventStoryMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 6,
  },
  eventStoryMetric: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  eventStoryReason: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 5,
  },
  eventStoryCaution: {
    color: '#9a3412',
  },
  eventSocialRow: {
    alignItems: 'center',
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 7,
  },
  eventSocialPill: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    color: '#9a3412',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  eventViewerStatus: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
  },
  eventFriendPreview: {
    color: '#0f766e',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 5,
  },
  eventRouteContext: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 5,
  },
  eventDescription: {
    color: '#31506b',
    fontSize: 12,
    lineHeight: 17,
    marginTop: 5,
  },
  eventFitExplanation: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 7,
  },
  eventInterestRow: {
    flexDirection: 'row',
    gap: 7,
    marginTop: 8,
  },
  eventInterestButton: {
    alignItems: 'center',
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    flex: 1,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  eventInterestButtonSelected: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
  },
  eventInterestText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  eventInterestTextSelected: {
    color: '#fffdf8',
  },
  eventActionRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 8,
  },
  eventLinkButton: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  eventReserveButton: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
  },
  eventLinkText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  eventReserveText: {
    color: '#fffdf8',
    fontSize: 12,
    fontWeight: '900',
  },
  eventSaveButton: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  eventSaveText: {
    color: '#9a3412',
    fontSize: 12,
    fontWeight: '900',
  },
  filterSection: {
    marginTop: 0,
    marginBottom: 8,
  },
  filterPanelHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#dff6f2',
    paddingHorizontal: 10,
    paddingVertical: 9,
    marginBottom: 8,
    shadowColor: '#123c69',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 5,
    elevation: 2,
  },
  filterPanel: {
    marginTop: 8,
  },
  filterTitle: {
    fontSize: 13,
    fontWeight: '900',
    color: '#134e4a',
  },
  filterSummary: {
    marginTop: 2,
    color: '#31506b',
    fontSize: 12,
  },
  dropdownButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    paddingHorizontal: 10,
    paddingVertical: 9,
    marginBottom: 6,
  },
  dropdownLabel: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '800',
  },
  dropdownValue: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  dropdownMenu: {
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fff',
    overflow: 'hidden',
    marginBottom: 8,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 10,
    paddingVertical: 9,
  },
  dropdownItemSelected: {
    backgroundColor: '#123c69',
  },
  dropdownItemDisabled: {
    backgroundColor: '#f9fafb',
  },
  dropdownItemText: {
    fontSize: 12,
    fontWeight: '800',
    color: '#123c69',
  },
  dropdownHelperText: {
    fontSize: 12,
    color: '#31506b',
  },
  dropdownItemTextDisabled: {
    color: '#a3a3a3',
  },
  dropdownItemTextSelected: {
    color: '#fff',
  },
  dropdownButtonDisabled: {
    opacity: 0.6,
  },
  scoutStylePanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 6,
    marginTop: 2,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  scoutStyleSummary: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  scoutStyleGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  scoutStyleChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: '48%',
    flexGrow: 1,
    paddingHorizontal: 9,
    paddingVertical: 8,
  },
  scoutStyleChipSelected: {
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
  },
  scoutStyleChipText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  scoutStyleChipTextSelected: {
    color: '#fffdf8',
  },
  scoutStyleChipHelper: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    marginTop: 2,
  },
  scoutStyleChipHelperSelected: {
    color: '#ffcf7a',
  },
  learnedRerankNotice: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  learnedRerankNoticeActive: {
    backgroundColor: '#e8f8fb',
    borderColor: '#123c69',
  },
  learnedRerankNoticeConstrained: {
    backgroundColor: '#fff7ed',
    borderColor: '#ff9f1c',
  },
  autoScoutLearnedSkipNotice: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    paddingHorizontal: 9,
    paddingVertical: 7,
  },
  autoScoutLearnedSkipKicker: {
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  autoScoutLearnedSkipText: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
    marginTop: 3,
  },
  learnedRerankNoticeHeader: {
    alignItems: 'flex-start',
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'space-between',
  },
  learnedRerankNoticeText: {
    color: '#9a3412',
    fontSize: 11,
    fontWeight: '800',
    lineHeight: 15,
  },
  learnedRerankNoticeTextWide: {
    flex: 1,
  },
  learnedRerankNoticeTextActive: {
    color: '#123c69',
  },
  learnedRerankNoticeTextConstrained: {
    color: '#9a3412',
  },
  learnedRerankRefreshButton: {
    backgroundColor: '#fffdf8',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    flexShrink: 0,
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  learnedRerankRefreshText: {
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  learnedGuardChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
    marginTop: 7,
  },
  learnedGuardChip: {
    borderRadius: 999,
    fontSize: 9,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
    textTransform: 'uppercase',
  },
  learnedGuardChipPass: {
    backgroundColor: '#dff6f2',
    color: '#134e4a',
  },
  learnedGuardChipWatch: {
    backgroundColor: '#ffedd5',
    color: '#9a3412',
  },
  learnedGuardChipConstrained: {
    backgroundColor: '#fee2e2',
    color: '#991b1b',
  },
  tastePanel: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 6,
    marginTop: 2,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  tasteSummary: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
    maxWidth: 215,
  },
  tasteStatusPill: {
    alignItems: 'center',
    backgroundColor: '#123c69',
    borderColor: '#ff9f1c',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  tasteStatusText: {
    color: '#fffdf8',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tasteConfidenceText: {
    color: '#ffcf7a',
    fontSize: 10,
    fontWeight: '900',
    marginTop: 1,
  },
  tasteChipBlock: {
    marginTop: 9,
  },
  tasteChipLabel: {
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  tasteChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 5,
  },
  tasteChip: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 9,
    paddingVertical: 5,
  },
  tasteChipAvoid: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    color: '#9a3412',
  },
  tasteEmpty: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 8,
  },
  tasteMetricRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 9,
  },
  tasteMetric: {
    color: '#134e4a',
    fontSize: 10,
    fontWeight: '900',
  },
  tastePartyNote: {
    color: '#31506b',
    fontSize: 10,
    fontWeight: '800',
    lineHeight: 14,
    marginTop: 7,
  },
  tasteBlendBox: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 9,
    padding: 8,
  },
  tasteBlendRow: {
    alignItems: 'flex-start',
    borderTopColor: '#d6edf3',
    borderTopWidth: 1,
    flexDirection: 'row',
    gap: 8,
    marginTop: 7,
    paddingTop: 7,
  },
  tasteBlendNameBlock: {
    flex: 1,
  },
  tasteBlendName: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  tasteBlendStatus: {
    color: '#31506b',
    fontSize: 9,
    fontWeight: '800',
    marginTop: 1,
    textTransform: 'uppercase',
  },
  tasteBlendTags: {
    alignItems: 'flex-end',
    flex: 1,
    gap: 4,
  },
  tasteBlendTag: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 9,
    fontWeight: '900',
    maxWidth: 130,
    overflow: 'hidden',
    paddingHorizontal: 7,
    paddingVertical: 3,
  },
  tasteBlendTagMuted: {
    color: '#6b7280',
    fontSize: 9,
    fontWeight: '800',
  },
  hardConstraintPanel: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: 6,
    marginTop: 2,
    paddingHorizontal: 10,
    paddingVertical: 10,
  },
  hardConstraintSummary: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 2,
  },
  hardConstraintGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 9,
  },
  hardConstraintChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  hardConstraintChipSelected: {
    backgroundColor: '#fff7ed',
    borderColor: '#e6534b',
  },
  hardConstraintText: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
  },
  hardConstraintTextSelected: {
    color: '#9a3412',
  },
  partyPanel: {
    borderWidth: 1,
    borderColor: '#87cfe1',
    borderRadius: 8,
    backgroundColor: '#fffdf8',
    paddingHorizontal: 10,
    paddingVertical: 10,
    marginTop: 2,
  },
  partyHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 10,
  },
  partySummary: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 2,
  },
  friendChipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 7,
    marginTop: 10,
  },
  friendChip: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  friendChipSelected: {
    backgroundColor: '#123c69',
    borderColor: '#123c69',
  },
  friendChipText: {
    color: '#123c69',
    fontSize: 12,
    fontWeight: '900',
  },
  friendChipTextSelected: {
    color: '#fffdf8',
  },
  partyEmpty: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '700',
    marginTop: 9,
  },
  groupFitBox: {
    backgroundColor: '#e8f8fb',
    borderColor: '#87cfe1',
    borderRadius: 8,
    borderWidth: 1,
    marginTop: 10,
    padding: 8,
  },
  groupFitHeader: {
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  groupFitTitle: {
    color: '#123c69',
    fontSize: 11,
    fontWeight: '900',
    textTransform: 'uppercase',
  },
  groupFitScore: {
    color: '#134e4a',
    fontSize: 11,
    fontWeight: '900',
  },
  groupFitMessage: {
    color: '#31506b',
    fontSize: 11,
    fontWeight: '700',
    lineHeight: 15,
    marginTop: 5,
  },
  groupFitMemberRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginTop: 7,
  },
  groupFitMemberPill: {
    backgroundColor: '#fffdf8',
    borderColor: '#87cfe1',
    borderRadius: 999,
    borderWidth: 1,
    color: '#123c69',
    fontSize: 10,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  groupFitMemberPillLow: {
    backgroundColor: '#fff7ed',
    borderColor: '#ffcf7a',
    color: '#9a3412',
  },
  groupFitMemberPillLearning: {
    backgroundColor: '#e8f8fb',
    borderColor: '#123c69',
    color: '#123c69',
  },
  partyCoverageList: {
    backgroundColor: '#fffdf8',
    borderColor: '#b6e2da',
    borderRadius: 8,
    borderWidth: 1,
    gap: 5,
    marginTop: 8,
    paddingHorizontal: 8,
    paddingVertical: 7,
  },
  partyCoverageRow: {
    alignItems: 'center',
    flexDirection: 'row',
    gap: 8,
  },
  partyCoverageName: {
    color: '#123c69',
    flexBasis: 82,
    flexShrink: 0,
    fontSize: 10,
    fontWeight: '900',
  },
  partyCoveragePick: {
    color: '#134e4a',
    flex: 1,
    fontSize: 10,
    fontWeight: '800',
  },
  partyCoveragePickWeak: {
    color: '#9a3412',
  },
  tagInfo: {
    color: '#6b7280',
    fontSize: 12,
    fontWeight: '900',
  },
  button: {
    backgroundColor: '#0f766e',
    paddingVertical: 9,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 8,
    shadowColor: '#0f766e',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.18,
    shadowRadius: 6,
    elevation: 3,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '900',
  },
});

export default HomeScreen;
