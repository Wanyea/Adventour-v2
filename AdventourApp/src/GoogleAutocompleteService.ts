import axios from 'axios';
import Config from './Config';

type Location = {
  latitude: number;
  longitude: number;
};

class GoogleAutocompleteService {
  static baseUrl = 'https://maps.googleapis.com/maps/api';

  static async fetchAutocompleteSuggestions(input: string, location: Location) {
    try {
      const response = await axios.get(`${this.baseUrl}/place/autocomplete/json`, {
        params: {
          input,
          location: `${location.latitude},${location.longitude}`,
          radius: 3200, // Search radius in meters (approximately 2 miles)
          key: Config.GOOGLE_API_KEY,
        },
      });
      return response.data.predictions;
    } catch (error) {
      console.error('Error fetching autocomplete suggestions:', error);
      return [];
    }
  }
}

export default GoogleAutocompleteService;
