import { Filter, RotateCcw } from "lucide-react";

const STATUS_OPTIONS = [
  "Tất cả",
  "Chờ xử lý",
  "Đang xử lý",
  "Tạm dừng",
  "Hoàn thành",
  "Hủy",
];

const DEPARTMENT_OPTIONS = ["Tất cả", "A", "B", "C"];

export default function TaskFilter({ filters, onChange, onReset }) {
  const handleChange = (event) => {
    const { name, value } = event.target;
    onChange({ ...filters, [name]: value });
  };

  return (
    <section className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-end sm:justify-between">
      <div className="grid gap-3 sm:grid-cols-2">
        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Trạng thái
          <select
            name="status"
            value={filters.status}
            onChange={handleChange}
            className="h-10 min-w-48 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          >
            {STATUS_OPTIONS.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>

        <label className="grid gap-1 text-sm font-medium text-slate-700">
          Phòng ban
          <select
            name="department"
            value={filters.department}
            onChange={handleChange}
            className="h-10 min-w-40 rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 outline-none transition focus:border-sky-500 focus:ring-2 focus:ring-sky-100"
          >
            {DEPARTMENT_OPTIONS.map((department) => (
              <option key={department} value={department}>
                {department}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex gap-2">
        <div className="hidden h-10 items-center gap-2 rounded-md bg-slate-50 px-3 text-sm font-medium text-slate-600 sm:flex">
          <Filter className="h-4 w-4" aria-hidden="true" />
          Bộ lọc
        </div>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
        >
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          Đặt lại
        </button>
      </div>
    </section>
  );
}
