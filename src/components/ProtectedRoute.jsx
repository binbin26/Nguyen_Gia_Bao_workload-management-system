import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({
  allowedRoles = ["manager"],
  children,
}) {
  const location = useLocation();
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

  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }

  if (allowedRoles.length > 0 && !allowedRoles.includes(user?.role)) {
    return <Navigate to="/login" replace />;
  }

  return children || <Outlet />;
}
