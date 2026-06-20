import auth, { FirebaseAuthTypes } from '@react-native-firebase/auth';
import AsyncStorage from '@react-native-async-storage/async-storage';
import axios from 'axios';
import Config from '../Config';

export interface User {
  id: number;
  firebase_uid: string;
  email: string;
  username: string;
  display_name: string;
  profile_picture?: string;
  preferences?: string[];
}

class AuthService {
  private currentUser: User | null = null;
  private authStateListener: (() => void) | null = null;
  private isDevAuth = Config.API_AUTH_MODE === 'dev';

  constructor() {
    // Set up axios interceptor to include auth token
    axios.interceptors.request.use(
      async (config) => {
        const token = await this.getIdToken();
        if (token) {
          config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
      },
      (error) => {
        return Promise.reject(error);
      }
    );
  }

  async signInWithEmail(email: string, password: string): Promise<User> {
    try {
      if (this.isDevAuth) {
        const user = await this.getDevUser();
        this.currentUser = user;
        return user;
      }

      const userCredential = await auth().signInWithEmailAndPassword(email, password);
      const user = await this.getOrCreateUser(userCredential.user);
      this.currentUser = user;
      return user;
    } catch (error) {
      console.error('Sign in error:', error);
      throw error;
    }
  }

  async signUpWithEmail(email: string, password: string, displayName: string): Promise<User> {
    try {
      if (this.isDevAuth) {
        const user = await this.getDevUser(displayName);
        this.currentUser = user;
        return user;
      }

      const userCredential = await auth().createUserWithEmailAndPassword(email, password);
      
      // Update display name
      await userCredential.user.updateProfile({
        displayName: displayName
      });

      const user = await this.getOrCreateUser(userCredential.user);
      this.currentUser = user;
      return user;
    } catch (error) {
      console.error('Sign up error:', error);
      throw error;
    }
  }

  async signOut(): Promise<void> {
    try {
      if (!this.isDevAuth) {
        await auth().signOut();
      }
      this.currentUser = null;
      await AsyncStorage.removeItem('user_id');
      await AsyncStorage.removeItem('auth_token');
    } catch (error) {
      console.error('Sign out error:', error);
      throw error;
    }
  }

  async getIdToken(): Promise<string | null> {
    if (this.isDevAuth) {
      return Config.getDevAuthHeader()?.replace('Bearer ', '') || null;
    }

    try {
      const currentFirebaseUser = auth().currentUser;
      if (currentFirebaseUser) {
        return await currentFirebaseUser.getIdToken();
      }
      return null;
    } catch (error) {
      console.error('Get ID token error:', error);
      return null;
    }
  }

  async getCurrentUser(): Promise<User | null> {
    if (this.currentUser) {
      return this.currentUser;
    }

    if (this.isDevAuth) {
      try {
        const user = await this.getDevUser();
        this.currentUser = user;
        return user;
      } catch (error) {
        console.error('Get dev user error:', error);
        return null;
      }
    }

    const currentFirebaseUser = auth().currentUser;
    if (currentFirebaseUser) {
      try {
        const user = await this.getOrCreateUser(currentFirebaseUser);
        this.currentUser = user;
        return user;
      } catch (error) {
        console.error('Get current user error:', error);
        return null;
      }
    }

    return null;
  }

  private async getOrCreateUser(firebaseUser: FirebaseAuthTypes.User): Promise<User> {
    try {
      // Try to get user from backend
      const token = await firebaseUser.getIdToken();
      const response = await axios.get(`${Config.BACKEND_BASE_URL}/user/${firebaseUser.uid}`, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });

      if (response.data.user) {
        return response.data.user;
      }

      // If user doesn't exist, create them
      const createResponse = await axios.post(`${Config.BACKEND_BASE_URL}/user`, {
        firebase_uid: firebaseUser.uid,
        email: firebaseUser.email,
        display_name: firebaseUser.displayName || firebaseUser.email?.split('@')[0] || 'User'
      }, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });

      return createResponse.data.user;
    } catch (error) {
      console.error('Get or create user error:', error);
      throw error;
    }
  }

  onAuthStateChanged(callback: (user: User | null) => void): () => void {
    if (this.isDevAuth) {
      let active = true;
      this.getDevUser()
        .then((user) => {
          if (!active) {
            return;
          }
          this.currentUser = user;
          callback(user);
        })
        .catch((error) => {
          console.error('Dev auth state change error:', error);
          if (active) {
            callback(null);
          }
        });

      const unsubscribe = () => {
        active = false;
      };
      this.authStateListener = unsubscribe;
      return unsubscribe;
    }

    const unsubscribe = auth().onAuthStateChanged(async (firebaseUser) => {
      if (firebaseUser) {
        try {
          const user = await this.getOrCreateUser(firebaseUser);
          this.currentUser = user;
          callback(user);
        } catch (error) {
          console.error('Auth state change error:', error);
          callback(null);
        }
      } else {
        this.currentUser = null;
        callback(null);
      }
    });

    this.authStateListener = unsubscribe;
    return unsubscribe;
  }

  async resetPassword(email: string): Promise<void> {
    if (this.isDevAuth) {
      return;
    }

    try {
      await auth().sendPasswordResetEmail(email);
    } catch (error) {
      console.error('Reset password error:', error);
      throw error;
    }
  }

  async updateProfile(updates: { display_name?: string; profile_picture?: string }): Promise<User> {
    try {
      const token = await this.getIdToken();
      if (!token) {
        throw new Error('No authentication token');
      }

      const response = await axios.put(`${Config.BACKEND_BASE_URL}/user/profile`, updates, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });

      const updatedUser = response.data.user;
      this.currentUser = updatedUser;
      return updatedUser;
    } catch (error) {
      console.error('Update profile error:', error);
      throw error;
    }
  }

  private async getDevUser(displayName?: string): Promise<User> {
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/user/dev`, {
      email: Config.DEV_AUTH_EMAIL,
      display_name: displayName || Config.DEV_AUTH_EMAIL.split('@')[0],
    });

    return response.data.user;
  }
}

export default new AuthService();
