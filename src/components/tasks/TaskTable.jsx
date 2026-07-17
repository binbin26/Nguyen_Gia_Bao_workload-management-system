import { Eye, FileText, LoaderCircle } from "lucide-react";

const STATUS_TONES = {
  "Chờ xử lý": "bg-slate-100 text-slate-700 ring-slate-200",
  "Đang xử lý": "bg-sky-50 text-sky-700 ring-sky-200",
  "Tạm dừng": "bg-amber-50 text-amber-700 ring-amber-200",
  "Hoàn thành": "bg-emerald-50 text-emerald-700 ring-emerald-200",
  Hủy: "bg-red-50 text-red-700 ring-red-200",
};

function taskIdOf(task) {
  return task?.id || task?._id || task?.task_code || "";
}

function StatusBadge({ status }) {
  const tone = STATUS_TONES[status] || STATUS_TONES["Chờ xử lý"];

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${tone}`}
    >
      {status || "Không rõ"}
    </span>
  );
}

export default function TaskTable({ tasks, isLoading, onSelectTask }) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-left">
          <thead className="bg-slate-50">
            <tr>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-normal text-slate-500">
                Mã hồ sơ
              </th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-normal text-slate-500">
                Trạng thái
              </th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-normal text-slate-500">
                Bước hiện tại
              </th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-normal text-slate-500">
                Phòng ban
              </th>
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-normal text-slate-500">
                Cán bộ phụ trách
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-normal text-slate-500">
                Hành động
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 bg-white">
            {isLoading ? (
              <tr>
                <td colSpan={6} className="px-4 py-14 text-center">
                  <div className="inline-flex items-center gap-2 text-sm font-medium text-slate-500">
                    <LoaderCircle
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                    Đang tải danh sách hồ sơ
                  </div>
                </td>
              </tr>
            ) : tasks.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-14 text-center">
                  <div className="mx-auto flex max-w-sm flex-col items-center gap-2 text-slate-500">
                    <FileText className="h-8 w-8" aria-hidden="true" />
                    <p className="text-sm font-medium">
                      Không có hồ sơ phù hợp
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              tasks.map((task) => (
                <tr key={taskIdOf(task)} className="transition hover:bg-slate-50">
                  <td className="whitespace-nowrap px-4 py-4 text-sm font-semibold text-slate-950">
                    {task.task_code || taskIdOf(task)}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4">
                    <StatusBadge status={task.status} />
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-sm text-slate-700">
                    Bước {task.current_step || "-"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-sm text-slate-700">
                    {task.current_department || "-"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-sm text-slate-700">
                    {task.current_assigned_to || "Chưa gán"}
                  </td>
                  <td className="whitespace-nowrap px-4 py-4 text-right">
                    <button
                      type="button"
                      onClick={() => onSelectTask(task)}
                      className="inline-flex h-9 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 transition hover:border-sky-200 hover:bg-sky-50 hover:text-sky-700"
                    >
                      <Eye className="h-4 w-4" aria-hidden="true" />
                      Xem chi tiết
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
