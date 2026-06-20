const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');
const exclusionList = require('metro-config/src/defaults/exclusionList');

/**
 * Metro configuration
 * https://reactnative.dev/docs/metro
 *
 * @type {import('@react-native/metro-config').MetroConfig}
 */
const config = {
  projectRoot: __dirname,
  watchFolders: [],
  resolver: {
    blockList: exclusionList([
      /android[\/\\]build[\/\\].*/,
      /android[\/\\]app[\/\\]build[\/\\].*/,
      /ios[\/\\]build[\/\\].*/,
      /node_modules[\/\\].*[\/\\]android[\/\\]build[\/\\].*/,
      /node_modules[\/\\].*[\/\\]ios[\/\\]build[\/\\].*/,
      /node_modules[\/\\]@react-native[\/\\]gradle-plugin[\/\\]react-native-gradle-plugin[\/\\]build[\/\\].*/,
    ]),
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
