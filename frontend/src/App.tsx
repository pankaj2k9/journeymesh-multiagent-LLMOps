import { Navigate, Route, Routes, useLocation } from 'react-router-dom';

import { ADMIN_LOGIN_PATH, RequireAuth, USER_LOGIN_PATH } from './auth/RequireAuth';
import { Layout } from './components/layout/Layout';
import { AboutPage } from './pages/AboutPage';
import { AccountLayout } from './pages/account/AccountLayout';
import { AdminPage } from './pages/AdminPage';
import { BlogPage } from './pages/BlogPage';
import { BlogPostPage } from './pages/BlogPostPage';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SettingsPage } from './pages/SettingsPage';
import { SignInPage } from './pages/SignInPage';
import { TripPage } from './pages/TripPage';

/** Old addresses keep working, query string included. */
function Moved({ to }: { to: string }) {
  const { search } = useLocation();
  return <Navigate to={`${to}${search}`} replace />;
}

export function App() {
  return (
    <Layout>
      <Routes>
        {/* Public */}
        <Route path="/" element={<HomePage />} />
        <Route path="/trip/:tripId" element={<TripPage />} />
        <Route path="/blog" element={<BlogPage />} />
        <Route path="/blog/:slug" element={<BlogPostPage />} />
        <Route path="/about" element={<AboutPage />} />

        {/* Sign-in doors: one for travellers, one for administrators. */}
        <Route path={USER_LOGIN_PATH} element={<SignInPage audience="user" />} />
        <Route path={ADMIN_LOGIN_PATH} element={<SignInPage audience="admin" />} />

        {/* The signed-in area */}
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <AccountLayout />
            </RequireAuth>
          }
        >
          <Route index element={<DashboardPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
        <Route
          path="/admin"
          element={
            <RequireAuth role="ADMIN" loginPath={ADMIN_LOGIN_PATH}>
              <AccountLayout />
            </RequireAuth>
          }
        >
          <Route index element={<AdminPage />} />
        </Route>

        {/* Earlier addresses */}
        <Route path="/sign-in" element={<Moved to={USER_LOGIN_PATH} />} />
        <Route path="/history" element={<Moved to="/dashboard/history" />} />
        <Route path="/settings" element={<Moved to="/dashboard/settings" />} />

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
