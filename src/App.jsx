import { Navigate, Route, Routes } from "react-router-dom";

import MainLayout from "./components/layout/MainLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import { useAuth } from "./context/AuthContext";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import OverloadAlerts from "./pages/OverloadAlerts";
import TaskCenter from "./pages/TaskCenter";

function LoginRoute() {
  const { isAuthenticated, isInitializing, user } = useAuth();

  if (isInitializing) {
    return (
      <main className="grid min-h-screen place-items-center bg-slate-50">
        <p className="text-sm text-slate-600" role="status">
          Đang kiểm tra phiên đăng nhập...
        </p>
      </main>
    );
  }

  if (isAuthenticated && user?.role === "manager") {
    return <Navigate replace to="/dashboard" />;
  }

  return <Login />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate replace to="/login" />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route element={<ProtectedRoute allowedRoles={["manager"]} />}>
        <Route element={<MainLayout />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/tasks" element={<TaskCenter />} />
          <Route path="/alerts" element={<OverloadAlerts />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate replace to="/login" />} />
    </Routes>
  );
}
