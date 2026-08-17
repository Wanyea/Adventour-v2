import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Platform,
  ScrollView,
  ActivityIndicator,
  Image,
} from 'react-native';
import AuthService, { User } from '../src/services/AuthService';
import AnimatedClouds from '../src/components/AnimatedClouds';

const logo = require('../src/assets/brand/adventour-logo.png');
const googleSignInAndroid = require('../src/assets/brand/google-signin-android.png');
const googleSignUpAndroid = require('../src/assets/brand/google-signup-android.png');
const googleSignInIos = require('../src/assets/brand/google-signin-ios.png');
const googleSignUpIos = require('../src/assets/brand/google-signup-ios.png');

interface Props {
  onAuthSuccess: (user: User) => void;
}

const authErrorMessage = (error: any) => {
  const message = String(error?.message || error || '');
  const code = String(error?.code || '');

  if (code.includes('configuration-not') || message.includes('CONFIGURATION_NOT_FOUND')) {
    return 'Firebase Authentication is not fully configured for this project. In Firebase Console, enable Authentication and turn on the Email/Password sign-in provider, then rebuild the app.';
  }

  if (error?.response?.status === 401) {
    return 'Firebase sign-in worked, but Adventour could not verify the Firebase token on the backend. Restart the local backend so it loads FIREBASE_PROJECT_ID, then try again.';
  }

  if (code.includes('email-already-in-use')) {
    return 'That email already has an Adventour account. Try signing in instead.';
  }

  if (code.includes('invalid-email')) {
    return 'Please enter a valid email address.';
  }

  if (code.includes('weak-password')) {
    return 'Please use a stronger password. Firebase requires at least 6 characters.';
  }

  if (code.includes('wrong-password') || code.includes('invalid-credential') || code.includes('user-not-found')) {
    return 'That email or password did not match an Adventour account.';
  }

  return message || 'An error occurred during authentication.';
};

const isValidEmail = (value: string) =>
  /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());

const passwordChecks = (value: string) => ({
  length: value.length >= 8,
  lowercase: /[a-z]/.test(value),
  uppercase: /[A-Z]/.test(value),
  number: /\d/.test(value),
  special: /[^A-Za-z0-9]/.test(value),
});

const FirebaseAuthScreen: React.FC<Props> = ({ onAuthSuccess }) => {
  const [isSignUp, setIsSignUp] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const trimmedEmail = email.trim();
  const checks = passwordChecks(password);
  const passwordStrong = Object.values(checks).every(Boolean);
  const passwordsMatch = password.length > 0 && password === confirmPassword;
  const emailValid = isValidEmail(trimmedEmail);
  const signInValid = emailValid && password.length > 0;
  const signUpValid = emailValid && passwordStrong && passwordsMatch;
  const emailAuthDisabled = loading || googleLoading || (isSignUp ? !signUpValid : !signInValid);
  const googleAuthDisabled = loading || googleLoading;

  const handleAuth = async () => {
    if (emailAuthDisabled) {
      return;
    }
    
    setLoading(true);

    try {
      let user: User;
      
      if (isSignUp) {
        user = await AuthService.signUpWithEmail(trimmedEmail, password);
      } else {
        user = await AuthService.signInWithEmail(trimmedEmail, password);
      }

      onAuthSuccess(user);
    } catch (error: any) {
      console.error('Auth error:', error);
      Alert.alert(
        'Authentication Error',
        authErrorMessage(error)
      );
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    if (googleAuthDisabled) {
      return;
    }

    setGoogleLoading(true);

    try {
      const user = await AuthService.signInWithGoogle();
      onAuthSuccess(user);
    } catch (error: any) {
      if (String(error?.message || '').includes('cancelled')) {
        return;
      }

      console.error('Google auth error:', error);
      Alert.alert(
        'Google Sign-In Error',
        authErrorMessage(error)
      );
    } finally {
      setGoogleLoading(false);
    }
  };

  const handleForgotPassword = async () => {
    if (!email) {
      Alert.alert('Error', 'Please enter your email address first');
      return;
    }

    try {
      await AuthService.resetPassword(email);
      Alert.alert(
        'Password Reset',
        'A password reset email has been sent to your email address'
      );
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to send reset email');
    }
  };

  const googleButtonImage = Platform.select({
    ios: isSignUp ? googleSignUpIos : googleSignInIos,
    default: isSignUp ? googleSignUpAndroid : googleSignInAndroid,
  });

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.container}>
      <AnimatedClouds height={980} speed="slow" />
      <View style={styles.content}>
        <View style={styles.logoCard}>
          <Image source={logo} style={styles.logo} resizeMode="contain" />
          <Text style={styles.logoTagline}>Let us guide your adventure!</Text>
        </View>
        <Text style={styles.subtitle}>
          {isSignUp ? 'Create your account' : 'Welcome back!'}
        </Text>

        <TouchableOpacity
          style={[styles.googleButton, googleAuthDisabled && styles.googleButtonDisabled]}
          onPress={handleGoogleAuth}
          disabled={googleAuthDisabled}
          activeOpacity={0.86}
        >
          {googleLoading ? (
            <ActivityIndicator color="#123c69" />
          ) : (
            <Image source={googleButtonImage} style={styles.googleButtonImage} resizeMode="contain" />
          )}
        </TouchableOpacity>

        <View style={styles.dividerRow}>
          <View style={styles.dividerLine} />
          <Text style={styles.dividerText}>or use email</Text>
          <View style={styles.dividerLine} />
        </View>

        <TextInput
          style={styles.input}
          placeholder="Email"
          value={email}
          onChangeText={setEmail}
          keyboardType="email-address"
          autoCapitalize="none"
          autoCorrect={false}
        />
        {email.length > 0 && !emailValid ? (
          <Text style={styles.validationText}>Enter a valid email address.</Text>
        ) : null}

        <TextInput
          style={styles.input}
          placeholder="Password"
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          autoCapitalize="none"
          autoCorrect={false}
        />
        {isSignUp ? (
          <>
            <TextInput
              style={styles.input}
              placeholder="Confirm password"
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
            />
            <View style={styles.passwordHelp}>
              <Text style={[styles.passwordRule, checks.length && styles.passwordRuleMet]}>8+ characters</Text>
              <Text style={[styles.passwordRule, checks.lowercase && styles.passwordRuleMet]}>lowercase</Text>
              <Text style={[styles.passwordRule, checks.uppercase && styles.passwordRuleMet]}>uppercase</Text>
              <Text style={[styles.passwordRule, checks.number && styles.passwordRuleMet]}>number</Text>
              <Text style={[styles.passwordRule, checks.special && styles.passwordRuleMet]}>symbol</Text>
            </View>
            {confirmPassword.length > 0 && !passwordsMatch ? (
              <Text style={styles.validationText}>Passwords must match.</Text>
            ) : null}
          </>
        ) : null}

        <TouchableOpacity
          style={[styles.button, emailAuthDisabled && styles.buttonDisabled]}
          onPress={handleAuth}
          disabled={emailAuthDisabled}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.buttonText}>
              {isSignUp ? 'Sign Up' : 'Sign In'}
            </Text>
          )}
        </TouchableOpacity>

        {!isSignUp && (
          <TouchableOpacity
            style={styles.linkButton}
            onPress={handleForgotPassword}
          >
            <Text style={styles.linkText}>Forgot Password?</Text>
          </TouchableOpacity>
        )}

        <TouchableOpacity
          style={styles.switchButton}
          onPress={() => {
            setIsSignUp(!isSignUp);
            setPassword('');
            setConfirmPassword('');
          }}
        >
          <Text style={styles.switchText}>
            {isSignUp
              ? 'Already have an account? Sign In'
              : "Don't have an account? Sign Up"}
          </Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#bfeaf4',
  },
  container: {
    flexGrow: 1,
    backgroundColor: '#bfeaf4',
    overflow: 'hidden',
    position: 'relative',
  },
  content: {
    flex: 1,
    justifyContent: 'flex-start',
    padding: 20,
    paddingTop: 44,
    zIndex: 1,
  },
  logoCard: {
    alignSelf: 'center',
    width: '100%',
    minHeight: 170,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  logo: {
    width: 332,
    maxWidth: '96%',
    height: 144,
  },
  logoTagline: {
    color: '#f24d4d',
    fontFamily: Platform.select({
      ios: 'Snell Roundhand',
      android: 'cursive',
      default: 'serif',
    }),
    fontSize: 17,
    fontWeight: '700',
    marginTop: -2,
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 18,
    textAlign: 'center',
    marginTop: 0,
    marginBottom: 26,
    color: '#31506b',
    fontWeight: '700',
  },
  input: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#b6e2da',
    borderRadius: 8,
    padding: 15,
    marginBottom: 15,
    fontSize: 16,
  },
  validationText: {
    color: '#9f1239',
    fontSize: 12,
    fontWeight: '800',
    marginBottom: 10,
    marginTop: -9,
  },
  googleButton: {
    alignItems: 'center',
    alignSelf: 'center',
    backgroundColor: 'transparent',
    justifyContent: 'center',
    marginBottom: 16,
    minHeight: 44,
    width: 210,
  },
  googleButtonImage: {
    height: 44,
    width: 204,
  },
  googleButtonDisabled: {
    opacity: 0.48,
  },
  dividerRow: {
    alignItems: 'center',
    flexDirection: 'row',
    marginBottom: 16,
  },
  dividerLine: {
    backgroundColor: '#9ad8e8',
    flex: 1,
    height: 1,
  },
  dividerText: {
    color: '#31506b',
    fontSize: 12,
    fontWeight: '900',
    marginHorizontal: 10,
    textTransform: 'uppercase',
  },
  button: {
    backgroundColor: '#123c69',
    borderRadius: 8,
    padding: 15,
    alignItems: 'center',
    marginBottom: 15,
  },
  buttonDisabled: {
    backgroundColor: '#7aa6bd',
    opacity: 0.72,
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  linkButton: {
    alignItems: 'center',
    marginBottom: 20,
  },
  linkText: {
    color: '#0f766e',
    fontSize: 16,
    fontWeight: '800',
  },
  switchButton: {
    alignItems: 'center',
  },
  switchText: {
    color: '#31506b',
    fontSize: 16,
    fontWeight: '700',
  },
  passwordHelp: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 11,
    marginTop: -5,
  },
  passwordRule: {
    backgroundColor: 'rgba(255, 250, 243, 0.72)',
    borderColor: '#9ad8e8',
    borderRadius: 999,
    borderWidth: 1,
    color: '#6b7280',
    fontSize: 11,
    fontWeight: '900',
    overflow: 'hidden',
    paddingHorizontal: 8,
    paddingVertical: 4,
  },
  passwordRuleMet: {
    backgroundColor: '#dcfce7',
    borderColor: '#86efac',
    color: '#14532d',
  },
});

export default FirebaseAuthScreen;
