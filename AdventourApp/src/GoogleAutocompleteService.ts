import axios from 'axios';
import Config from './Config';

type Location = {
  latitude: number;
  longitude: number;
};

class GoogleAutocompleteService {
  static async fetchAutocompleteSuggestions(input: string, location?: Location | null, radiusMeters = 3200) {
    if (input.trim().length < 3) {
      return [];
    }

    try {
      const params: Record<string, string | number> = {
        input,
        radius_meters: radiusMeters,
      };
      if (location) {
        params.latitude = location.latitude;
        params.longitude = location.longitude;
      }

      const response = await axios.get(`${Config.BACKEND_BASE_URL}/api/places/autocomplete`, {
        params,
      });
      return response.data.predictions || [];
    } catch (error) {
      console.error('Error fetching autocomplete suggestions:', error);
      return [];
    }
  }
}

export default GoogleAutocompleteService;
