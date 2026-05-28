import { getJson, writeFormData, writeJson } from './client';

export function fetchCurrentUser() {
  return getJson('/api/auth/me/', 'Unable to read current user');
}

export function loginUser(credentials) {
  return writeJson('/api/auth/login/', 'POST', credentials, 'Unable to log in');
}

export function logoutUser() {
  return writeJson('/api/auth/logout/', 'POST', {}, 'Unable to log out');
}

export function registerUser(payload) {
  return writeJson('/api/auth/register/', 'POST', payload, 'Unable to register user');
}

export function fetchUsers() {
  return getJson('/api/auth/users/', 'Unable to read users');
}

export function createUser(payload) {
  return writeJson('/api/auth/users/', 'POST', payload, 'Unable to create user.');
}

export function fetchUserDirectory() {
  return getJson('/api/auth/directory/', 'Unable to read user directory');
}

export function setUserPassword(userId, password) {
  return writeJson(`/api/auth/users/${userId}/password/`, 'POST', { password }, 'Unable to update password');
}

export function uploadCurrentUserAvatar(file) {
  const formData = new FormData();
  formData.set('avatar', file);
  return writeFormData('/api/auth/me/avatar/', 'POST', formData, 'Unable to upload avatar');
}

export function deleteCurrentUserAvatar() {
  return writeJson('/api/auth/me/avatar/', 'DELETE', {}, 'Unable to remove avatar');
}
