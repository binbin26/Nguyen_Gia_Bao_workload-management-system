import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";

import {
  getStaffKpis,
  STAFF_KPI_QUERY_KEY,
} from "../services/analytics_api";

const percentageFormatter = new Intl.NumberFormat("vi-VN", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

function getEfficiencyPresentation(efficiencyRate) {
  if (efficiencyRate >= 100) {
    return {
      label: "Tuyệt vời",
      className: "text-emerald-700",
      badgeClassName: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    };
  }

  if (efficiencyRate >= 80) {
    return {
      label: "Ổn",
      className: "text-amber-700",
      badgeClassName: "bg-amber-50 text-amber-700 ring-amber-200",
    };
  }

  return {
    label: "Cần cải thiện",
    className: "text-red-700",
    badgeClassName: "bg-red-50 text-red-700 ring-red-200",
  };
}

function getErrorMessage(error) {
  const status = error?.response?.status;

  if (status === 401) {
    return "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.";
  }

  if (status === 403) {
    return "Chỉ tài khoản Manager mới được xem thống kê KPI.";
  }

  return "Không thể tải thống kê KPI. Vui lòng thử lại.";
}

export default function ManagerKPIDashboard() {
  const {
    data: staffKpis = [],
    error,
    isError,
    isFetching,
    isPending,
    refetch,
  } = useQuery({
    queryKey: STAFF_KPI_QUERY_KEY,
    queryFn: getStaffKpis,
  });

  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-col gap-3 border-b border-slate-200 px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div>
          <h2 className="text-base font-semibold text-slate-950">
            Hiệu suất nhân sự
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Tổng hợp các tác vụ hoàn thành trong 30 ngày gần nhất.
          </p>
        </div>

        <button
          type="button"
          onClick={() => refetch()}
          disabled={isFetching}
          className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
            aria-hidden="true"
          />
          Làm mới KPI
        </button>
      </div>

      {isPending ? (
        <div className="space-y-3 p-6" aria-label="Đang tải thống kê KPI">
          {[1, 2, 3].map((row) => (
            <div
              key={row}
              className="h-12 animate-pulse rounded-md bg-slate-100"
            />
          ))}
        </div>
      ) : null}

      {isError ? (
        <div className="m-4 rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 sm:m-6" role="alert">
          {getErrorMessage(error)}
        </div>
      ) : null}

      {!isPending && !isError && staffKpis.length === 0 ? (
        <p className="px-6 py-10 text-center text-sm text-slate-500">
          Chưa có tác vụ hoàn thành trong 30 ngày gần nhất.
        </p>
      ) : null}

      {!isPending && !isError && staffKpis.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
            <thead className="bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500">
              <tr>
                <th scope="col" className="px-4 py-3 sm:px-6">
                  Nhân viên
                </th>
                <th scope="col" className="whitespace-nowrap px-4 py-3">
                  Task hoàn thành
                </th>
                <th scope="col" className="whitespace-nowrap px-4 py-3">
                  Năng suất
                </th>
                <th scope="col" className="whitespace-nowrap px-4 py-3 sm:pr-6">
                  Chất lượng
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {staffKpis.map((staff) => {
                const efficiencyRate = Number(staff.efficiency_rate) || 0;
                const efficiency = getEfficiencyPresentation(efficiencyRate);
                const reworkedTasks = Number(staff.reworked_tasks) || 0;
                const totalTasks = Number(staff.total_tasks) || 0;
                const totalReworkCount = Number(staff.total_rework_count) || 0;
                const qualityScore = Number(staff.quality_score) || 0;

                return (
                  <tr key={staff.staff_id} className="hover:bg-slate-50/70">
                    <td className="px-4 py-4 sm:px-6">
                      <p className="font-semibold text-slate-900">
                        {staff.staff_name || staff.staff_id}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {staff.staff_id}
                        {staff.department ? ` · Phòng ${staff.department}` : ""}
                      </p>
                    </td>
                    <td className="px-4 py-4 font-medium tabular-nums text-slate-800">
                      {totalTasks}
                    </td>
                    <td className="px-4 py-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className={`font-bold tabular-nums ${efficiency.className}`}>
                          {percentageFormatter.format(efficiencyRate)}%
                        </span>
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset ${efficiency.badgeClassName}`}
                        >
                          {efficiency.label}
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        {staff.total_standard_hours}h định mức /{" "}
                        {staff.total_actual_hours}h thực tế
                      </p>
                    </td>
                    <td className="px-4 py-4 sm:pr-6">
                      <p
                        className={
                          reworkedTasks > 0
                            ? "font-semibold text-red-700"
                            : "font-semibold text-emerald-700"
                        }
                      >
                        {reworkedTasks} / {totalTasks} task phải làm lại
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {totalReworkCount} lượt trả lại · Điểm chất lượng{" "}
                        {percentageFormatter.format(qualityScore)}%
                      </p>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </section>
  );
}
