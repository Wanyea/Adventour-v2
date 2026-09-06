import axios from 'axios';
import Config from './Config';

export type LaunchSuggestion = {
  description: string;
  latitude: number;
  longitude: number;
  suggestion_id: string;
  source: string;
};

class LaunchLocationService {
  static async fetchAutocompleteSuggestions(input: string): Promise<LaunchSuggestion[]> {
    if (input.trim().length < 3) {
      return [];
    }

    const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/places/autocomplete`, {
      params: { input }, timeout: 12000,
    });
    return response.data.predictions || [];
  }
}

export default LaunchLocationService;
