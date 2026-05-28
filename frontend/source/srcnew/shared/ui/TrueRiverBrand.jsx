import { useRef, useState } from 'react';
import { LockOpenIcon, SettingsIcon, UserIcon } from './TablerIcons';
import { useOptionalAuth } from '../../app/AuthProvider';

export default function TrueRiverBrand({ mode = 'audio', className = '' }) {
  const auth = useOptionalAuth();
  const fileInputRef = useRef(null);
  const [isTrayOpen, setIsTrayOpen] = useState(false);
  const [avatarError, setAvatarError] = useState('');
  const [avatarBusy, setAvatarBusy] = useState(false);
  const user = auth?.user || null;
  const userLabel = user?.username || user?.email || 'User';

  async function handleLogout() {
    setIsTrayOpen(false);
    await auth?.logout?.();
  }

  async function handleAvatarChange(event) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    setAvatarError('');
    setAvatarBusy(true);
    try {
      await auth?.uploadAvatar?.(file);
    } catch (error) {
      setAvatarError(error.message || 'Avatar upload failed.');
    } finally {
      setAvatarBusy(false);
      event.target.value = '';
    }
  }

  async function handleAvatarDelete() {
    setAvatarError('');
    setAvatarBusy(true);
    try {
      await auth?.deleteAvatar?.();
    } catch (error) {
      setAvatarError(error.message || 'Unable to remove avatar.');
    } finally {
      setAvatarBusy(false);
    }
  }

  return (
    <div className={`tr-brand${className ? ` ${className}` : ''}`} data-brand-mode={mode} aria-label="trueRiver">
      <div className="tr-brand-wordmark">
        <div className="brand-logo brand-logo-inline">
          <span className="brand-logo-true">true</span>
          <span className="brand-logo-river-inline">River</span>
        </div>
        <span className="tr-brand-underline" aria-hidden="true" />
      </div>
      <div className="tr-brand-user-shell">
        <button
          type="button"
          className="tr-brand-user-placeholder"
          aria-label="User settings"
          onClick={() => setIsTrayOpen(true)}
        >
          {user?.avatar_url ? (
            <img src={user.avatar_url} alt="" />
          ) : (
            <UserIcon className="tr-brand-user-icon" />
          )}
        </button>
        {isTrayOpen ? (
          <div className="tr-user-tray-backdrop" role="presentation" onMouseDown={() => setIsTrayOpen(false)}>
            <aside className="tr-user-tray" role="dialog" aria-label="User settings" onMouseDown={(event) => event.stopPropagation()}>
              <div className="tr-user-tray-head">
                <div className="tr-user-tray-avatar">
                  {user?.avatar_url ? <img src={user.avatar_url} alt="" /> : <UserIcon className="tr-brand-user-icon" />}
                </div>
                <div>
                  <p className="panel-kicker">User settings</p>
                  <h2>{auth?.authenticated ? userLabel : 'Login required'}</h2>
                  <span>{auth?.authenticated ? (user?.email || 'trueRiver user') : 'No active session'}</span>
                </div>
              </div>
              <div className="tr-user-tray-fields">
                <span>Username <strong>{user?.username || '-'}</strong></span>
                <span>Email <strong>{user?.email || '-'}</strong></span>
                <span>Id <strong>{user?.id || '-'}</strong></span>
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp,image/gif"
                className="tr-user-tray-file"
                onChange={handleAvatarChange}
              />
              {avatarError ? <p className="tr-user-tray-error">{avatarError}</p> : null}
              {auth?.authenticated ? (
                <div className="tr-user-tray-actions">
                  <button type="button" onClick={() => fileInputRef.current?.click()} disabled={avatarBusy}>
                    <SettingsIcon className="tree-icon" />
                    <span>{avatarBusy ? 'Uploading...' : 'Upload avatar'}</span>
                  </button>
                  <button type="button" onClick={handleAvatarDelete} disabled={avatarBusy || !user?.avatar_url}>
                    <UserIcon className="tree-icon" />
                    <span>Remove avatar</span>
                  </button>
                  <button type="button" onClick={handleLogout}>
                    <LockOpenIcon className="tree-icon" />
                    <span>Logout</span>
                  </button>
                </div>
              ) : (
                <span className="tr-brand-user-menu-note">Sign in to use trueRiver.</span>
              )}
              <button type="button" className="tr-user-tray-close" onClick={() => setIsTrayOpen(false)}>
                Close
              </button>
            </aside>
          </div>
        ) : null}
      </div>
    </div>
  );
}
