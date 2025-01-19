import axios from 'axios';

const GOOGLE_API_KEY = 'AIzaSyD-RpERPi4HTQl3oiTWtbgZTXVu-kyN4as'; 

class GoogleAutocompleteService {
  static baseUrl = 'https://maps.googleapis.com/maps/api';

  // Autocomplete API: Suggest places based on user input
  static async fetchAutocompleteSuggestions(input, location) {
    try {
      const response = await axios.get(`${this.baseUrl}/place/autocomplete/json`, {
        params: {
          input,
          location: `${location.latitude},${location.longitude}`,
          radius: 10000, // Limit suggestions to a specific area
          key: GOOGLE_API_KEY,
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
