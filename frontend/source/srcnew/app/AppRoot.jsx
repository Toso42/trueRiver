import { useEffect, useState } from 'react';
import { RouteSwitch, RouterProvider, useRouter } from './simpleRouter';
import { AuthProvider, useAuth } from './AuthProvider';
import { I18nProvider, useT } from '../i18n/I18nProvider';
import AudioPage from '../pages/AudioPage';
import ArtistCardDebugPage from '../pages/ArtistCardDebugPage';
import ArtistCardSimplePage from '../pages/ArtistCardSimplePage';

function AuthGate({ children }) {
  const auth = useAuth();
  const t = useT();
  const [mode, setMode] = useState('login');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [email, setEmail] = useState('');
  const [formError, setFormError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (auth.loading) {
    return (
      <main className="auth-page">
        <div className="auth-shell">
          <section className="auth-copy">
            <img className="auth-logo-image" src="/trueriver-only-logo.png" alt="trueRiver" />
            <p>{t('Loading session...')}</p>
          </section>
        </div>
      </main>
    );
  }

  if (auth.authenticated) {
    return children;
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setFormError('');
    const nextUsername = username.trim();
    const nextPassword = password;
    if (!nextUsername || !nextPassword) {
      setFormError(t('Enter username and password.'));
      return;
    }
    setSubmitting(true);
    try {
      if (mode === 'register') {
        await auth.register({ username: nextUsername, password: nextPassword, email: email.trim() });
      } else {
        await auth.login({ username: nextUsername, password: nextPassword });
      }
    } catch (error) {
      setFormError(error.message || t('Sign in failed.'));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <section className="auth-copy">
          <img className="auth-logo-image" src="/trueriver-only-logo.png" alt="trueRiver" />
          <div>
            <p className="panel-kicker">{t('Private access')}</p>
            <h1>trueRiver</h1>
            <p>{t('Enter your library.')}</p>
          </div>
        </section>
        <section className="auth-panel">
          <div className="auth-panel-tabs" role="tablist" aria-label="Auth mode">
            <button type="button" className={mode === 'login' ? 'is-active' : ''} onClick={() => setMode('login')}>Login</button>
            <button type="button" className={mode === 'register' ? 'is-active' : ''} onClick={() => setMode('register')}>Register</button>
          </div>
          <form className="auth-form" onSubmit={handleSubmit}>
            <label>
              <span>User</span>
              <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" autoFocus />
            </label>
            {mode === 'register' ? (
              <label>
                <span>Email</span>
                <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" />
              </label>
            ) : null}
            <label>
              <span>Password</span>
              <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === 'register' ? 'new-password' : 'current-password'} />
            </label>
            {formError ? <p className="auth-error">{formError}</p> : null}
            <button type="submit" className="auth-submit" disabled={submitting}>
              {submitting ? t('Please wait...') : (mode === 'register' ? t('Create user') : t('Login'))}
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}

function AudioEntry({ replacePath = false }) {
  const router = useRouter();

  useEffect(() => {
    if (replacePath && router.pathname !== '/audio') {
      router.navigate('/audio', { replace: true });
    }
  }, [replacePath, router]);

  return <AudioPage />;
}

export default function AppRoot() {
  return (
    <I18nProvider>
      <AuthProvider>
        <AuthGate>
          <RouterProvider>
            <RouteSwitch
              routes={[
                { path: '/', element: <AudioEntry replacePath /> },
                { path: '/_triver/artist-card', element: <ArtistCardDebugPage /> },
                { path: '/_triver/artist-card-simple', element: <ArtistCardSimplePage /> },
                { path: '/audio/*', element: <AudioPage /> },
              ]}
              fallback={<AudioEntry replacePath />}
            />
          </RouterProvider>
        </AuthGate>
      </AuthProvider>
    </I18nProvider>
  );
}
