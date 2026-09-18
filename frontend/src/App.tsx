import { Route, Routes } from 'react-router-dom';

import { Layout } from './components/layout/Layout';
import { AboutPage } from './pages/AboutPage';
import { DashboardPage } from './pages/DashboardPage';
import { HistoryPage } from './pages/HistoryPage';
import { HomePage } from './pages/HomePage';
import { NotFoundPage } from './pages/NotFoundPage';
import { SettingsPage } from './pages/SettingsPage';
import { SignInPage } from './pages/SignInPage';
import { TripPage } from './pages/TripPage';

export function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/trip/:tripId" element={<TripPage />} />
        {/* Kept as a route of its own: the flat list is still the fastest way
            to find one journey among many, and the dashboard is a summary. */}
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/sign-in" element={<SignInPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Layout>
  );
}

export default App;
