import axios from 'axios';

// Use your actual API key here
const GOOGLE_PLACES_API_KEY = 'AIzaSyD5ywCTflow8-iHPmoIIMKxjYeM4eooD8E';  

export const fetchPlaces = async (selectedTags, location) => {
  try {
    console.log("Selected Tags:", selectedTags);
    console.log("Location:", location);

    const response = await axios.get(
      `https://maps.googleapis.com/maps/api/place/nearbysearch/json`,
      {
        params: {
          location: `${location.latitude},${location.longitude}`, // User's current location
          radius: 5000, // Radius in meters (adjust based on how far you want to search)
          type: selectedTags.join('|'), // Tags to filter by
          key: GOOGLE_PLACES_API_KEY, // Your API key
        }
      }
    );

    console.log("API Response:", response.data.results); // Log the response data
    return response.data.results; // Return list of places
  } catch (error) {
    console.error('Error fetching places:', error); // Log any errors
    return [];
  }
};
