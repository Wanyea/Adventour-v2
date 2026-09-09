import React from 'react';
import renderer, { act } from 'react-test-renderer';
import { Alert, TextInput, TouchableOpacity } from 'react-native';
import HomeCityEditor from './HomeCityEditor';
import AuthService from '../services/AuthService';

jest.mock('../services/AuthService', () => ({
  __esModule: true,
  default: { updateProfile: jest.fn() },
}));

const updatedUser = {
  id: 1,
  firebase_uid: 'user',
  email: 'user@example.com',
  username: 'user',
  display_name: 'User',
  home_city: 'Montréal, Québec, Canada',
};

const pressText = (view: renderer.ReactTestRenderer, label: string) => {
  const button = view.root.findAllByType(TouchableOpacity).find((item) => item.findAllByType('Text' as any).some((text: any) => text.props.children === label));
  if (!button) {
    throw new Error(`Missing ${label} button`);
  }
  button.props.onPress();
};

beforeEach(() => {
  jest.clearAllMocks();
  jest.spyOn(console, 'error').mockImplementation(() => undefined);
});

afterEach(() => jest.restoreAllMocks());

test('saves a trimmed Unicode home city only after the server confirms it', async () => {
  const onUserUpdated = jest.fn();
  jest.mocked(AuthService.updateProfile).mockResolvedValue(updatedUser);
  const view = renderer.create(<HomeCityEditor userId={1} homeCity={null} onUserUpdated={onUserUpdated} />);

  act(() => pressText(view, 'Edit'));
  act(() => view.root.findByType(TextInput).props.onChangeText('  Montréal, Québec, Canada  '));
  await act(async () => pressText(view, 'Save'));

  expect(AuthService.updateProfile).toHaveBeenCalledWith({ home_city: 'Montréal, Québec, Canada' });
  expect(onUserUpdated).toHaveBeenCalledWith(updatedUser);
});

test('clears an existing home city with null', async () => {
  jest.mocked(AuthService.updateProfile).mockResolvedValue({ ...updatedUser, home_city: null });
  const view = renderer.create(<HomeCityEditor userId={1} homeCity="Montréal, Québec, Canada" />);

  act(() => pressText(view, 'Edit'));
  act(() => pressText(view, 'Clear'));
  await act(async () => pressText(view, 'Save'));

  expect(AuthService.updateProfile).toHaveBeenCalledWith({ home_city: null });
});

test('cancelling discards a draft without saving', () => {
  const view = renderer.create(<HomeCityEditor userId={1} homeCity="Accra, Ghana" />);

  act(() => pressText(view, 'Edit'));
  act(() => view.root.findByType(TextInput).props.onChangeText('Kumasi, Ghana'));
  act(() => pressText(view, 'Cancel'));

  expect(AuthService.updateProfile).not.toHaveBeenCalled();
  expect(view.root.findAllByType(TextInput)).toHaveLength(0);
  expect(view.root.findAllByType('Text' as any).some((text: any) => text.props.children === 'Accra, Ghana')).toBe(true);
});

test('keeps the draft open and reports an error when saving fails', async () => {
  jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
  jest.mocked(AuthService.updateProfile).mockRejectedValue(new Error('offline'));
  const onUserUpdated = jest.fn();
  const view = renderer.create(<HomeCityEditor userId={1} homeCity="Accra, Ghana" onUserUpdated={onUserUpdated} />);

  act(() => pressText(view, 'Edit'));
  act(() => view.root.findByType(TextInput).props.onChangeText('Kumasi, Ghana'));
  await act(async () => pressText(view, 'Save'));

  expect(onUserUpdated).not.toHaveBeenCalled();
  expect(view.root.findByType(TextInput).props.value).toBe('Kumasi, Ghana');
  expect(Alert.alert).toHaveBeenCalledWith('Unable to save home base', 'Your home city or town could not be saved. Please try again.');
});
