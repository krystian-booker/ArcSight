import { Routes, Route } from 'react-router-dom';
import { QueryProvider, ToastProvider } from './context';
import { AppLayout } from './components/layout';
import DashboardPage from './pages/DashboardPage';
import CamerasPage from './pages/CamerasPage';
import CalibrationPage from './pages/CalibrationPage';
import MonitoringPage from './pages/MonitoringPage';
import SettingsPage from './pages/SettingsPage';

export default function App() {
  return (
    <QueryProvider>
      <ToastProvider>
        <AppLayout>
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/cameras" element={<CamerasPage />} />
            <Route path="/calibration" element={<CalibrationPage />} />
            <Route path="/monitoring" element={<MonitoringPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </AppLayout>
      </ToastProvider>
    </QueryProvider>
  );
}
