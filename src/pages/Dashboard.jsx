import { AlertTriangle, ListChecks, RefreshCw, UserCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import StatWidget from "../components/dashboard/StatWidget";
import WorkloadHeatmap from "../components/dashboard/WorkloadHeatmap";
import ManagerKPIDashboard from "../components/ManagerKPIDashboard";
import { getStaffs } from "../services/staff_api.jsx";

export default function Dashboard() {
  const [staffs, setStaffs] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const loadStaffs = async () => {
    setIsLoading(true);
    setError("");

    try {
      const data = await getStaffs();
      setStaffs(data);
    } catch (err) {
      if (err.response?.status === 401 || err.response?.status === 403) {
        setError("Phiên đăng nhập không còn hợp lệ hoặc không đủ quyền truy cập.");
      } else {
        setError("Không thể tải dữ liệu nhân sự. Vui lòng thử lại.");
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadStaffs();
  }, []);

  const stats = useMemo(() => {
    return staffs.reduce(
      (summary, staff) => {
        const currentTasks = Number(
          staff?.workload_caps?.current_daily_tasks || 0,
        );

        return {
          totalTasks: summary.totalTasks + currentTasks,
          availableStaff:
            summary.availableStaff + (staff.status === "Sẵn sàng" ? 1 : 0),
          overloadedStaff:
            summary.overloadedStaff + (staff.status === "Quá tải" ? 1 : 0),
        };
      },
      {
        totalTasks: 0,
        availableStaff: 0,
        overloadedStaff: 0,
      },
    );
  }, [staffs]);

  return (
    <>
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-sky-700">Tổng quan vận hành</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">
            Dashboard tải lượng nhân sự
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Giám sát trạng thái xử lý, số tác vụ và mức sử dụng giờ làm việc
            trong ngày của từng phòng ban.
          </p>
        </div>

        <button
          type="button"
          onClick={loadStaffs}
          disabled={isLoading}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${isLoading ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Làm mới
        </button>
      </header>

      {error ? (
        <section
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
          role="alert"
        >
          {error}
        </section>
      ) : null}

      <section className="grid gap-4 md:grid-cols-3">
        <StatWidget
          title="Tác vụ đang chạy hôm nay"
          value={isLoading ? "..." : stats.totalTasks}
          description="Tổng current_daily_tasks của toàn bộ nhân sự."
          icon={ListChecks}
          tone="sky"
        />
        <StatWidget
          title="Nhân sự sẵn sàng"
          value={isLoading ? "..." : stats.availableStaff}
          description="Có thể tiếp nhận hồ sơ mới trong ngày."
          icon={UserCheck}
          tone="green"
        />
        <StatWidget
          title="Đang quá tải"
          value={isLoading ? "..." : stats.overloadedStaff}
          description="Cần theo dõi hoặc điều phối lại tải lượng."
          icon={AlertTriangle}
          tone={stats.overloadedStaff > 0 ? "red" : "amber"}
        />
      </section>

      {isLoading ? (
        <section className="grid gap-4 xl:grid-cols-3">
          {["A", "B", "C"].map((department) => (
            <div
              key={department}
              className="h-80 animate-pulse rounded-lg border border-slate-200 bg-white"
            />
          ))}
        </section>
      ) : (
        <WorkloadHeatmap staffs={staffs} />
      )}

      <ManagerKPIDashboard />
    </>
  );
}
