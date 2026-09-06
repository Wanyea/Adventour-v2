import axios from 'axios';
import Config from '../Config';
import { AdventourSession, AdventourStop } from '../types/Adventour';
import { Place } from '../types/Place';

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
      decision_id: place.decision_id,
    });
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async arrive(sessionId: number, stopId: number): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/arrive`);
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async navigate(sessionId: number, stopId: number): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/navigate`);
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async completeStop(sessionId: number, stopId: number, rating: number, notes = ''): Promise<{ adventour: AdventourSession; stop: AdventourStop }> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/stops/${stopId}/complete`, { rating, notes });
    return { adventour: response.data.adventour, stop: response.data.stop };
  }

  static async complete(sessionId: number): Promise<AdventourSession> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/api/adventours/${sessionId}/complete`);
    return response.data.adventour;
  }
}

export default AdventourService;
