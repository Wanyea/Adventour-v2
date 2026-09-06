import axios from 'axios';
import Config from '../Config';
import { Place } from '../types/Place';

export type PlaceEventType = 'impression' | 'accept' | 'reject' | 'navigate' | 'arrival' | 'rate' | 'save' | 'share' | 'closed_report';

export const recordPlaceEvent = async (place: Pick<Place, 'place_id' | 'decision_id'>, eventType: PlaceEventType, context = 'solo') => {
  const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/events`, {
    place_id: place.place_id,
    decision_id: place.decision_id,
    event_type: eventType,
    context,
  });
  return response.data.event;
};
