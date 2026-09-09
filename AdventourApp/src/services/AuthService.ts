import auth, { FirebaseAuthTypes } from '@react-native-firebase/auth';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { GoogleSignin, statusCodes } from '@react-native-google-signin/google-signin';
import axios from 'axios';
import Config from '../Config';

export interface User {
  id: number;
  firebase_uid: string;
  email: string;
  username: string;
  display_name: string;
  date_of_birth?: string;
  profile_picture?: string;
  preferences?: string[];
  profile_complete?: boolean;
  home_city?: string | null;
}

class AuthService {
  private currentUser: User | null = null;
  private sessionVersion = 0;
  private authStateListener: (() => void) | null = null;
  private isDevAuth = Config.API_AUTH_MODE === 'dev';

  private setCurrentUser(user: User | null, newSession = false) {
    const identityChanged = this.currentUser?.firebase_uid !== user?.firebase_uid;
    this.currentUser = user;
    if (identityChanged || newSession) {
      this.sessionVersion += 1;
    }
  }

  private isCurrentSession(version: number, firebaseUid?: string) {
    return this.sessionVersion === version && this.currentUser?.firebase_uid === firebaseUid;
  }

  constructor() {
    if (Config.GOOGLE_WEB_CLIENT_ID) {
      GoogleSignin.configure({
        webClientId: Config.GOOGLE_WEB_CLIENT_ID,
      });
    }

    // Set up axios interceptor to include auth token
    axios.interceptors.request.use(
      async (config) => {
        const token = await this.getIdToken();
        if (token && !config.headers.Authorization) {
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
        const user = await this.getDevUser(undefined, email);
        this.setCurrentUser(user);
        return user;
      }

      const userCredential = await auth().signInWithEmailAndPassword(email, password);
      const user = await this.getOrCreateUser(userCredential.user);
      this.setCurrentUser(user);
      return user;
    } catch (error) {
      console.error('Sign in error:', error);
      throw error;
    }
  }

  async signUpWithEmail(email: string, password: string, displayName?: string): Promise<User> {
    try {
      if (this.isDevAuth) {
        const user = await this.getDevUser(displayName, email);
        this.setCurrentUser(user);
        return user;
      }

      const userCredential = await auth().createUserWithEmailAndPassword(email, password);
      
      // Update display name
      const trimmedDisplayName = displayName?.trim();
      if (trimmedDisplayName) {
        await userCredential.user.updateProfile({
          displayName: trimmedDisplayName,
        });
      }

      const user = await this.getOrCreateUser(userCredential.user);
      this.setCurrentUser(user);
      return user;
    } catch (error) {
      console.error('Sign up error:', error);
      throw error;
    }
  }

  async signInWithGoogle(displayName?: string): Promise<User> {
    try {
      if (this.isDevAuth) {
        const user = await this.getDevUser(displayName || 'Google Dev User', 'google-dev@adventour.local');
        this.setCurrentUser(user);
        return user;
      }

      if (!Config.GOOGLE_WEB_CLIENT_ID) {
        throw new Error('Google sign-in is missing GOOGLE_WEB_CLIENT_ID in the app environment.');
      }

      await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
      const googleUser = await GoogleSignin.signIn();
      const idToken = googleUser.data?.idToken;

      if (!idToken) {
        throw new Error('Google sign-in did not return an ID token.');
      }

      const googleCredential = auth.GoogleAuthProvider.credential(idToken);
      const userCredential = await auth().signInWithCredential(googleCredential);
      let user = await this.getOrCreateUser(userCredential.user);
      const trimmedDisplayName = displayName?.trim();
      if (trimmedDisplayName && trimmedDisplayName !== user.display_name) {
        this.setCurrentUser(user);
        user = await this.updateProfile({ display_name: trimmedDisplayName });
      }
      this.setCurrentUser(user);
      return user;
    } catch (error: any) {
      if (error?.code === statusCodes.SIGN_IN_CANCELLED) {
        throw new Error('Google sign-in was cancelled.');
      }

      console.error('Google sign in error:', error);
      throw error;
    }
  }

  async signOut(): Promise<void> {
    try {
      if (!this.isDevAuth) {
        if (GoogleSignin.hasPreviousSignIn()) {
          await GoogleSignin.signOut();
        }
        await auth().signOut();
      }
      this.setCurrentUser(null);
      if (this.isDevAuth) {
        await AsyncStorage.setItem('dev_auth_email', '__signed_out__');
      }
      await AsyncStorage.removeItem('user_id');
      await AsyncStorage.removeItem('auth_token');
    } catch (error) {
      console.error('Sign out error:', error);
      throw error;
    }
  }

  async deleteAccount(): Promise<void> {
    try {
      const token = await this.getIdToken();
      if (!token) {
        throw new Error('No authentication token');
      }

      await axios.post(`${Config.BACKEND_BASE_URL}/user/me/reset`, {}, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (this.isDevAuth) {
        await AsyncStorage.setItem('dev_auth_email', '__signed_out__');
      }

      if (!this.isDevAuth) {
        const firebaseUser = auth().currentUser;
        if (firebaseUser) {
          await firebaseUser.delete();
        }

        if (GoogleSignin.hasPreviousSignIn()) {
          await GoogleSignin.signOut();
        }
      }

      this.setCurrentUser(null);
      await AsyncStorage.removeItem('user_id');
      await AsyncStorage.removeItem('auth_token');
    } catch (error) {
      console.error('Delete account error:', error);
      throw error;
    }
  }

  async getIdToken(): Promise<string | null> {
    if (this.isDevAuth) {
      const email = this.currentUser?.email || await AsyncStorage.getItem('dev_auth_email') || Config.DEV_AUTH_EMAIL;
      return email === '__signed_out__' ? null : `dev:${email}`;
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
        if (await AsyncStorage.getItem('dev_auth_email') === '__signed_out__') {
          return null;
        }
        const user = await this.getDevUser();
        this.setCurrentUser(user);
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
        this.setCurrentUser(user);
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
        if (firebaseUser.displayName && !response.data.user.display_name) {
          const updateResponse = await axios.post(`${Config.BACKEND_BASE_URL}/user`, {
            display_name: firebaseUser.displayName,
          }, {
            headers: {
              Authorization: `Bearer ${token}`
            }
          });
          return updateResponse.data.user;
        }
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
      this.getCurrentUser()
        .then((user) => {
          if (!active) {
            return;
          }
          this.setCurrentUser(user);
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
          this.setCurrentUser(user);
          callback(user);
        } catch (error) {
          console.error('Auth state change error:', error);
          callback(null);
        }
      } else {
        this.setCurrentUser(null);
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

  async updateProfile(updates: { display_name?: string; date_of_birth?: string; profile_picture?: string; home_city?: string | null }): Promise<User> {
    try {
      const sessionVersion = this.sessionVersion;
      const firebaseUid = this.currentUser?.firebase_uid;
      const token = await this.getIdToken();
      if (!token) {
        throw new Error('No authentication token');
      }
      if (!this.isCurrentSession(sessionVersion, firebaseUid)) {
        throw new Error('Your account changed before the profile update could be sent.');
      }

      const response = await axios.put(`${Config.BACKEND_BASE_URL}/user/profile`, updates, {
        headers: {
          Authorization: `Bearer ${token}`
        }
      });

      const updatedUser = response.data.user;
      if (!this.isCurrentSession(sessionVersion, firebaseUid) || updatedUser.firebase_uid !== firebaseUid) {
        throw new Error('Your account changed before the profile update completed.');
      }
      this.setCurrentUser(updatedUser);
      return updatedUser;
    } catch (error) {
      console.error('Update profile error:', error);
      throw error;
    }
  }

  private async getDevUser(displayName?: string, emailOverride?: string): Promise<User> {
    const devEmail = emailOverride || await AsyncStorage.getItem('dev_auth_email') || Config.DEV_AUTH_EMAIL;
    const response = await axios.post(`${Config.BACKEND_BASE_URL}/user/dev`, {
      email: devEmail,
      ...(displayName ? { display_name: displayName } : {}),
    });
    await AsyncStorage.setItem('dev_auth_email', devEmail);
    return response.data.user;
  }
}

export default new AuthService();
