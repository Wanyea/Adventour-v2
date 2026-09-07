import NativeConfig from 'react-native-config';

class Config {
  static PILOT_BUILD = NativeConfig.APP_VARIANT === 'pilot' &&
    Boolean(NativeConfig.PILOT_ID && NativeConfig.APP_BUILD_ID);
  static PILOT_ID = NativeConfig.PILOT_ID || '';
  static APP_BUILD_ID = NativeConfig.APP_BUILD_ID || '';
  static BACKEND_BASE_URL =
    NativeConfig.BACKEND_BASE_URL || 'http://10.0.2.2:8080';
  static GOOGLE_API_KEY = NativeConfig.GOOGLE_API_KEY || '';
  static GOOGLE_WEB_CLIENT_ID = NativeConfig.GOOGLE_WEB_CLIENT_ID || '';
  static API_AUTH_MODE = NativeConfig.API_AUTH_MODE || 'firebase';
  static DEV_AUTH_EMAIL = NativeConfig.DEV_AUTH_EMAIL || 'dev@adventour.local';

  static getDevAuthHeader() {
    if (Config.API_AUTH_MODE !== 'dev') {
      return undefined;
    }

    return `Bearer dev:${Config.DEV_AUTH_EMAIL}`;
  }
}

export default Config;
