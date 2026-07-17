import {
  CheckCircle2,
  CircleDashed,
  Clock3,
  LoaderCircle,
  PauseCircle,
  PlayCircle,
  X,
  XCircle,
} from "lucide-react";

const STATUS_META = {
  "Chờ xử lý": {
    icon: Clock3,
    node: "bg-slate-100 text-slate-600 ring-slate-200",
    badge: "bg-slate-100 text-slate-700 ring-slate-200",
  },
  "Đang xử lý": {
    icon: PlayCircle,
    node: "bg-sky-100 text-sky-700 ring-sky-300",
    badge: "bg-sky-50 text-sky-700 ring-sky-200",
  },
  "Tạm dừng": {
    icon: PauseCircle,
    node: "bg-amber-100 text-amber-700 ring-amber-300",
    badge: "bg-amber-50 text-amber-700 ring-amber-200",
  },
  "Hoàn thành": {
    icon: CheckCircle2,
    node: "bg-emerald-100 text-emerald-700 ring-emerald-300",
    badge: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  },
  Hủy: {
    icon: XCircle,
    node: "bg-red-100 text-red-700 ring-red-300",
    badge: "bg-red-50 text-red-700 ring-red-200",
  },
};

function taskIdOf(task) {
  return task?.id || task?._id || "";
}

function formatDateTime(value) {
  if (!value) {
    return "Chưa hoàn thành";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Không rõ thời gian";
  }

  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Asia/Ho_Chi_Minh",
  }).format(date);
}

function TimelineNode({ entry, isLast }) {
  const meta = STATUS_META[entry?.status] || STATUS_META["Chờ xử lý"];
  const Icon = meta.icon || CircleDashed;
  const isActive = entry?.status === "Đang xử lý";

  return (
    <li className="relative grid grid-cols-[2.5rem_1fr] gap-3 pb-6 last:pb-0">
      {!isLast ? (
        <span className="absolute left-5 top-10 h-full w-px bg-slate-200" />
      ) : null}
      <div
        className={`relative z-10 flex h-10 w-10 items-center justify-center rounded-full ring-4 ${meta.node} ${
          isActive ? "animate-pulse" : ""
        }`}
      >
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>

      <div className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-950">
              Bước {entry?.step_number || "-"} · Phòng ban{" "}
              {entry?.department || "-"}
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Cán bộ: {entry?.assigned_to || "Chưa gán"}
            </p>
          </div>
          <span
            className={`inline-flex w-fit items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ${meta.badge}`}
          >
            {entry?.status || "Không rõ"}
          </span>
        </div>
        <p className="mt-3 text-sm text-slate-500">
          Hoàn thành: {formatDateTime(entry?.completed_at)}
        </p>
      </div>
    </li>
  );
}

export default function TaskDetailDrawer({
  task,
  isOpen,
  isAdvancing,
  onClose,
  onNextStep,
}) {
  if (!isOpen || !task) {
    return null;
  }

  const history = Array.isArray(task.workflow_history)
    ? task.workflow_history
    : [];
  const canAdvance = task.status === "Đang xử lý";

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 cursor-default bg-slate-950/35"
        onClick={onClose}
        aria-label="Đóng chi tiết hồ sơ"
      />

      <aside className="absolute right-0 top-0 flex h-full w-full max-w-2xl flex-col bg-slate-50 shadow-2xl">
        <header className="border-b border-slate-200 bg-white px-5 py-4">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-sky-700">
                {taskIdOf(task)}
              </p>
              <h2 className="mt-1 text-xl font-semibold text-slate-950">
                Hồ sơ {task.task_code || taskIdOf(task)}
              </h2>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 items-center justify-center rounded-md border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-100 hover:text-slate-950"
              aria-label="Đóng"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>

          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p className="text-xs font-medium text-slate-500">Trạng thái</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {task.status || "Không rõ"}
              </p>
            </div>
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p className="text-xs font-medium text-slate-500">Bước</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {task.current_step || "-"}
              </p>
            </div>
            <div className="rounded-md bg-slate-50 px-3 py-2">
              <p className="text-xs font-medium text-slate-500">Phòng ban</p>
              <p className="mt-1 text-sm font-semibold text-slate-900">
                {task.current_department || "-"}
              </p>
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-5">
          {history.length > 0 ? (
            <ol>
              {history.map((entry, index) => (
                <TimelineNode
                  key={`${entry?.step_number || index}-${entry?.department || "dept"}`}
                  entry={entry}
                  isLast={index === history.length - 1}
                />
              ))}
            </ol>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
              <CircleDashed
                className="mx-auto h-8 w-8 text-slate-400"
                aria-hidden="true"
              />
              <p className="mt-3 text-sm font-medium text-slate-600">
                Chưa có dữ liệu tiến trình
              </p>
            </div>
          )}
        </div>

        {canAdvance ? (
          <footer className="border-t border-slate-200 bg-white px-5 py-4">
            <button
              type="button"
              onClick={() => onNextStep(task)}
              disabled={isAdvancing}
              className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-md bg-sky-600 px-4 text-sm font-semibold text-white transition hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {isAdvancing ? (
                <LoaderCircle
                  className="h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
              ) : (
                <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
              )}
              Hoàn thành bước hiện tại
            </button>
          </footer>
        ) : null}
      </aside>
    </div>
  );
}
