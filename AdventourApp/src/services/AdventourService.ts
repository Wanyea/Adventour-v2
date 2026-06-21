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

  static async complete(sessionId: number): Promise<AdventourSession> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/complete`);
    return response.data.adventour;
  }
}

export default AdventourService;
