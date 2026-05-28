import { createContext, useContext, useEffect, useMemo, useState } from 'react';

const RouterContext = createContext(null);

function normalizePath(pathname) {
  if (!pathname || pathname === '/') {
    return '/';
  }
  return pathname.replace(/\/+$/, '') || '/';
}

function matchPattern(pattern, pathname) {
  const normalizedPattern = normalizePath(pattern);
  const normalizedPath = normalizePath(pathname);

  if (normalizedPattern.endsWith('/*')) {
    const prefix = normalizedPattern.slice(0, -2);
    return normalizedPath === prefix || normalizedPath.startsWith(`${prefix}/`);
  }

  return normalizedPattern === normalizedPath;
}

export function RouterProvider({ children }) {
  const [pathname, setPathname] = useState(() => normalizePath(window.location.pathname));

  useEffect(() => {
    function handlePopState() {
      setPathname(normalizePath(window.location.pathname));
    }

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const value = useMemo(
    () => ({
      pathname,
      navigate(nextPath, options = {}) {
        const normalizedNextPath = normalizePath(nextPath);
        const method = options.replace ? 'replaceState' : 'pushState';
        window.history[method]({}, '', normalizedNextPath);
        setPathname(normalizedNextPath);
      },
    }),
    [pathname],
  );

  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function RouteSwitch({ routes, fallback = null }) {
  const router = useRouter();
  const match = routes.find((route) => matchPattern(route.path, router.pathname));
  return match ? match.element : fallback;
}

export function LinkButton({ to, className = '', children }) {
  const router = useRouter();
  const isActive = router.pathname === normalizePath(to);

  return (
    <button
      type="button"
      className={`${className}${isActive ? ' is-active' : ''}`.trim()}
      onClick={() => router.navigate(to)}
    >
      {children}
    </button>
  );
}

export function useRouter() {
  const context = useContext(RouterContext);
  if (!context) {
    throw new Error('useRouter must be used inside RouterProvider');
  }
  return context;
}

export function usePathname() {
  return useRouter().pathname;
}
