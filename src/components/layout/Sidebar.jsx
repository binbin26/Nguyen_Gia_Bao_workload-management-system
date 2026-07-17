import {
  AlertTriangle,
  Files,
  LayoutDashboard,
  LogOut,
  ShieldCheck,
} from "lucide-react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import { useAuth } from "../../context/AuthContext";

const menuItems = [
  {
    label: "Tổng quan",
    icon: LayoutDashboard,
    to: "/dashboard",
    enabled: true,
  },
  {
    label: "Danh sách Hồ sơ",
    icon: Files,
    to: "/tasks",
    enabled: true,
  },
  {
    label: "Cảnh báo Quá tải",
    icon: AlertTriangle,
    to: "/alerts",
    enabled: true,
  },
];

function SidebarItem({ item }) {
  const location = useLocation();
  const Icon = item.icon;
  const isActive = item.enabled && location.pathname === item.to;

  const className = [
    "flex h-11 w-full items-center gap-3 rounded-md px-3 text-sm font-medium transition",
    isActive
      ? "bg-sky-50 text-sky-700 ring-1 ring-sky-100"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-950",
    !item.enabled ? "cursor-not-allowed opacity-55 hover:bg-transparent" : "",
  ].join(" ");

  if (!item.enabled) {
    return (
      <button type="button" className={className} disabled>
        <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
        <span className="truncate">{item.label}</span>
      </button>
    );
  }

  return (
    <NavLink to={item.to} className={className}>
      <Icon className="h-5 w-5 shrink-0" aria-hidden="true" />
      <span className="truncate">{item.label}</span>
    </NavLink>
  );
}

export default function Sidebar() {
  const navigate = useNavigate();
  const { logout, user } = useAuth();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <aside className="border-b border-slate-200 bg-white lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:flex lg:w-72 lg:flex-col lg:border-b-0 lg:border-r">
      <div className="flex h-16 items-center gap-3 border-b border-slate-200 px-4 sm:px-6">
        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-sky-600 text-white">
          <ShieldCheck className="h-5 w-5" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-slate-950">
            VNPT Workforce
          </p>
          <p className="truncate text-xs text-slate-500">Manager Console</p>
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto px-4 py-3 sm:px-6 lg:flex-1 lg:flex-col lg:gap-1 lg:overflow-visible lg:py-5">
        {menuItems.map((item) => (
          <SidebarItem key={item.label} item={item} />
        ))}
      </div>

      <div className="hidden border-t border-slate-200 p-4 lg:block">
        <div className="mb-3 rounded-md bg-slate-50 px-3 py-2">
          <p className="truncate text-sm font-medium text-slate-800">
            {user?.username || "Manager"}
          </p>
          <p className="text-xs capitalize text-slate-500">
            {user?.role || "manager"}
          </p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="flex h-11 w-full items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition hover:border-red-200 hover:bg-red-50 hover:text-red-700"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Đăng xuất
        </button>
      </div>

      <div className="border-t border-slate-200 px-4 py-3 sm:px-6 lg:hidden">
        <button
          type="button"
          onClick={handleLogout}
          className="flex h-10 w-full items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700"
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          Đăng xuất
        </button>
      </div>
    </aside>
  );
}
