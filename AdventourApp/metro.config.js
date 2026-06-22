const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

const blockList = [
  /[/\\]android[/\\]build[/\\].*/,
  /[/\\]android[/\\]app[/\\]build[/\\].*/,
  /[/\\]ios[/\\]build[/\\].*/,
  /[/\\]node_modules[/\\].*[/\\]android[/\\]build[/\\].*/,
  /[/\\]node_modules[/\\].*[/\\]ios[/\\]build[/\\].*/,
  /[/\\]node_modules[/\\]@react-native[/\\]gradle-plugin[/\\]react-native-gradle-plugin[/\\]build[/\\].*/,
  /[/\\]node_modules[/\\]@react-native-async-storage[/\\]async-storage[/\\]android[/\\]build[/\\].*/,
];

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
    blockList: new RegExp(blockList.map((pattern) => pattern.source).join('|')),
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
