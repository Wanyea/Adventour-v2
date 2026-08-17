import axios from 'axios';
import Config from '../Config';
import { AdventourSession, AdventourStop } from '../types/Adventour';
import { Place } from '../types/Place';

const displayPayloadForPlace = (place: Place) => ({
  name: place.name,
  vicinity: place.vicinity,
  types: place.types,
  category: place.category,
  tag_groups: place.tag_groups || [],
  photo_url: place.photo_url ? place.photo_url.replace(Config.BACKEND_BASE_URL, '') : undefined,
  photo_attributions: place.photo_attributions || [],
  rating: place.rating,
  user_ratings_total: place.user_ratings_total,
  price_level: place.price_level,
  latitude: place.latitude,
  longitude: place.longitude,
});

class AdventourService {
  static async getActive(): Promise<AdventourSession | null> {
    const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/adventours/active`);
    return response.data.adventour || null;
  }

  static async start(title?: string): Promise<AdventourSession> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours`, { title });
    return response.data.adventour;
  }

  static async startFromItinerary(payload: {
    title: string;
    destination?: string;
    companion_user_ids?: number[];
    price_breakdown?: any;
    booking_plan?: any;
    scoring_profile?: string;
    trip_style?: string;
    pace?: string;
    budget_profile?: string;
    query_tags?: string[];
    route_readiness?: any;
    route_explanation?: any;
    launch_checklist?: any;
    local_events?: any;
    trip_packet?: any;
    scenario_readiness?: any;
    filter_summary?: any;
    learned_rerank?: any;
    swap_summary?: any;
    destination_scout?: any;
    reservation_ids?: number[];
    stops: any[];
  }): Promise<AdventourSession> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/from-itinerary`, payload);
    return response.data.adventour;
  }

  static async addStop(sessionId: number, place: Place): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops`, {
      place_id: place.place_id,
      provider: place.provider,
      provider_place_id: place.provider_place_id,
      source: 'recommendation_deck',
      display: displayPayloadForPlace(place),
    });
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async arrive(sessionId: number, stopId: number): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/arrive`);
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async completeStop(sessionId: number, stopId: number, rating: number): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/complete`, { rating });
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async swapStop(sessionId: number, stopId: number, alternativeIndex: number): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/swap`, {
      alternative_index: alternativeIndex,
    });
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async complete(sessionId: number): Promise<AdventourSession> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/complete`);
    return response.data.adventour;
  }
}

export default AdventourService;
