import { useEffect, useState } from 'react';
import { createUser, fetchUsers, setUserPassword } from '../../../../api/auth';
import AudioContentScaffold from '../AudioContentScaffold';
import { useAuth } from '../../../../app/AuthProvider';

export default function UsersView() {
  const auth = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pageError, setPageError] = useState('');
  const [editingUserId, setEditingUserId] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [createForm, setCreateForm] = useState({
    username: '',
    email: '',
    password: '',
    passwordConfirm: '',
    is_staff: false,
    is_superuser: false,
  });
  const [createMessage, setCreateMessage] = useState('');
  const [createBusy, setCreateBusy] = useState(false);
  const isAdmin = Boolean(auth.user?.is_staff || auth.user?.is_superuser);
  const canCreateAdmin = Boolean(auth.user?.is_superuser);

  function loadUsers() {
    if (!isAdmin) {
      setUsers([]);
      setLoading(false);
      return () => {};
    }
    let cancelled = false;
    setLoading(true);
    setPageError('');
    fetchUsers()
      .then((payload) => {
        if (!cancelled) {
          setUsers(Array.isArray(payload) ? payload : []);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setPageError(error.message || 'Unable to read users');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }

  useEffect(() => {
    return loadUsers();
  }, [isAdmin]);

  function updateCreateForm(key, value) {
    setCreateForm((current) => {
      const next = { ...current, [key]: value };
      if (key === 'is_superuser' && value) {
        next.is_staff = true;
      }
      if (key === 'is_staff' && !value) {
        next.is_superuser = false;
      }
      return next;
    });
  }

  async function handleCreateUser(event) {
    event.preventDefault();
    setCreateMessage('');
    const username = createForm.username.trim();
    if (!username) {
      setCreateMessage('Username is required.');
      return;
    }
    if (createForm.password.length < 8) {
      setCreateMessage('The password must be at least 8 characters.');
      return;
    }
    if (createForm.password !== createForm.passwordConfirm) {
      setCreateMessage('Passwords do not match.');
      return;
    }
    setCreateBusy(true);
    try {
      const payload = await createUser({
        username,
        email: createForm.email.trim(),
        password: createForm.password,
        is_staff: canCreateAdmin && createForm.is_staff,
        is_superuser: canCreateAdmin && createForm.is_superuser,
      });
      const nextUser = payload.user;
      if (nextUser) {
        setUsers((current) => [...current.filter((user) => user.id !== nextUser.id), nextUser].sort((left, right) => (
          String(left.username || '').localeCompare(String(right.username || ''))
        )));
      } else {
        loadUsers();
      }
      setCreateForm({
        username: '',
        email: '',
        password: '',
        passwordConfirm: '',
        is_staff: false,
        is_superuser: false,
      });
      setCreateMessage('User created.');
    } catch (error) {
      setCreateMessage(error.message || 'Unable to create user.');
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleSetPassword(event, userId) {
    event.preventDefault();
    setPasswordMessage('');
    if (password.length < 8) {
      setPasswordMessage('The password must be at least 8 characters.');
      return;
    }
    if (password !== passwordConfirm) {
      setPasswordMessage('Passwords do not match.');
      return;
    }
    setPasswordBusy(true);
    try {
      await setUserPassword(userId, password);
      setPassword('');
      setPasswordConfirm('');
      setEditingUserId('');
      setPasswordMessage('Password updated.');
    } catch (error) {
      setPasswordMessage(error.message || 'Unable to update password.');
    } finally {
      setPasswordBusy(false);
    }
  }

  function startPasswordEdit(userId) {
    setEditingUserId(userId);
    setPassword('');
    setPasswordConfirm('');
    setPasswordMessage('');
  }

  return (
    <AudioContentScaffold title="Users" description="Registered trueRiver accounts.">
      {!isAdmin ? <p className="metadata-error">Admin permissions required.</p> : null}
      {pageError ? <p className="metadata-error">{pageError}</p> : null}
      {loading ? <p className="empty-state">Loading users...</p> : null}
      {!loading && isAdmin ? (
        <>
          <form className="users-create-panel" onSubmit={handleCreateUser}>
            <div className="users-create-head">
              <h3>Create user</h3>
              {createMessage ? <p className="users-password-message">{createMessage}</p> : null}
            </div>
            <div className="users-create-grid">
              <label>
                <span>Username</span>
                <input
                  type="text"
                  value={createForm.username}
                  onChange={(event) => updateCreateForm('username', event.target.value)}
                  autoComplete="username"
                  disabled={createBusy}
                />
              </label>
              <label>
                <span>Email</span>
                <input
                  type="email"
                  value={createForm.email}
                  onChange={(event) => updateCreateForm('email', event.target.value)}
                  autoComplete="email"
                  disabled={createBusy}
                />
              </label>
              <label>
                <span>Initial password</span>
                <input
                  type="password"
                  value={createForm.password}
                  onChange={(event) => updateCreateForm('password', event.target.value)}
                  autoComplete="new-password"
                  disabled={createBusy}
                />
              </label>
              <label>
                <span>Confirm</span>
                <input
                  type="password"
                  value={createForm.passwordConfirm}
                  onChange={(event) => updateCreateForm('passwordConfirm', event.target.value)}
                  autoComplete="new-password"
                  disabled={createBusy}
                />
              </label>
              <label className="users-check-row">
                <input
                  type="checkbox"
                  checked={createForm.is_staff}
                  onChange={(event) => updateCreateForm('is_staff', event.target.checked)}
                  disabled={createBusy || !canCreateAdmin}
                />
                <span>Admin account</span>
              </label>
              <label className="users-check-row">
                <input
                  type="checkbox"
                  checked={createForm.is_superuser}
                  onChange={(event) => updateCreateForm('is_superuser', event.target.checked)}
                  disabled={createBusy || !canCreateAdmin}
                />
                <span>Superuser account</span>
              </label>
              <span className="users-actions">
                <button type="submit" disabled={createBusy}>{createBusy ? 'Creating...' : 'Create user'}</button>
              </span>
            </div>
          </form>
          <div className="users-table" role="table" aria-label="Users">
            <div className="users-table-row users-table-head" role="row">
              <span role="columnheader">User</span>
              <span role="columnheader">Email</span>
              <span role="columnheader">Role</span>
              <span role="columnheader">Password</span>
            </div>
            {passwordMessage ? <p className="users-password-message">{passwordMessage}</p> : null}
            {users.map((user) => (
              editingUserId === user.id ? (
                <form key={user.id} className="users-table-row users-password-row" role="row" onSubmit={(event) => handleSetPassword(event, user.id)}>
                  <strong role="cell">{user.username}</strong>
                  <label role="cell">
                    <span>New password</span>
                    <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="new-password" />
                  </label>
                  <label role="cell">
                    <span>Confirm</span>
                    <input type="password" value={passwordConfirm} onChange={(event) => setPasswordConfirm(event.target.value)} autoComplete="new-password" />
                  </label>
                  <span role="cell" className="users-actions">
                    <button type="submit" disabled={passwordBusy}>{passwordBusy ? 'Saving...' : 'Save'}</button>
                    <button type="button" onClick={() => setEditingUserId('')}>Cancel</button>
                  </span>
                </form>
              ) : (
                <div key={user.id} className="users-table-row" role="row">
                  <strong role="cell">{user.username}</strong>
                  <span role="cell">{user.email || '-'}</span>
                  <span role="cell">{user.is_superuser ? 'Superuser' : user.is_staff ? 'Admin' : 'User'}</span>
                  <span role="cell" className="users-actions">
                    <button type="button" onClick={() => startPasswordEdit(user.id)}>Set password</button>
                  </span>
                </div>
              )
            ))}
          </div>
        </>
      ) : null}
    </AudioContentScaffold>
  );
}
