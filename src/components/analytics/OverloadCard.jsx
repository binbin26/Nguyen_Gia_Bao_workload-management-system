import { Bot, CalendarClock, FileWarning, Zap } from "lucide-react";

function alertIdOf(alert) {
  return alert?.id || alert?._id || alert?.log_id || "";
}

function getSuggestions(alert) {
  const rawSuggestions = alert?.suggestions || alert?.ai_suggestions || [];

  if (!Array.isArray(rawSuggestions)) {
    return [];
  }

  return rawSuggestions.filter((candidate) => {
    const score = Number(candidate?.matching_score || 0);
    return candidate?.status !== "Nghỉ phép" && score > 0;
  });
}

function formatDateTime(value) {
  if (!value) {
    return "Không rõ thời gian";
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

function getImpactedStaffName(alert) {
  return (
    alert?.staff_name ||
    alert?.staff_fullname ||
    alert?.staff?.fullname ||
    alert?.task?.current_assigned_to ||
    alert?.staff_id ||
    "Chưa xác định"
  );
}

function getTaskLabel(alert) {
  const task = alert?.task || {};
  return task.task_code || task.task_id || alert?.task_id || "Chưa xác định";
}

export default function OverloadCard({ alert, onResolve }) {
  const alertId = alertIdOf(alert);
  const suggestions = getSuggestions(alert);
  const task = alert?.task || {};

  return (
    <article className="rounded-lg border border-amber-200 bg-amber-50 p-5 shadow-sm ring-1 ring-amber-100">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-md bg-amber-100 px-2.5 py-1 text-xs font-semibold text-amber-800 ring-1 ring-amber-200">
              <FileWarning className="h-3.5 w-3.5" aria-hidden="true" />
              Cần điều phối
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-md bg-white/75 px-2.5 py-1 text-xs font-medium text-slate-600 ring-1 ring-amber-100">
              <CalendarClock className="h-3.5 w-3.5" aria-hidden="true" />
              {formatDateTime(alert?.timestamp || alert?.created_at)}
            </span>
          </div>

          <h2 className="mt-4 text-lg font-semibold tracking-normal text-slate-950">
            {getImpactedStaffName(alert)}
          </h2>
          <p className="mt-1 text-sm leading-6 text-slate-600">
            {alert?.trigger_reason || "Hệ thống phát hiện nguy cơ quá tải."}
          </p>
        </div>

        <button
          type="button"
          onClick={() => onResolve(alert)}
          disabled={!alertId}
          className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-md bg-slate-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          <Bot className="h-4 w-4" aria-hidden="true" />
          Xử lý điều phối
        </button>
      </div>

      <dl className="mt-5 grid gap-3 sm:grid-cols-3">
        <div className="rounded-md bg-white/80 px-3 py-2 ring-1 ring-amber-100">
          <dt className="text-xs font-medium text-slate-500">Mã hồ sơ</dt>
          <dd className="mt-1 truncate text-sm font-semibold text-slate-950">
            {getTaskLabel(alert)}
          </dd>
        </div>
        <div className="rounded-md bg-white/80 px-3 py-2 ring-1 ring-amber-100">
          <dt className="text-xs font-medium text-slate-500">Phòng ban</dt>
          <dd className="mt-1 text-sm font-semibold text-slate-950">
            {task.current_department || alert?.department || "-"}
          </dd>
        </div>
        <div className="rounded-md bg-white/80 px-3 py-2 ring-1 ring-amber-100">
          <dt className="text-xs font-medium text-slate-500">AI đề xuất</dt>
          <dd className="mt-1 flex items-center gap-2 text-sm font-semibold text-slate-950">
            <Zap className="h-4 w-4 text-amber-600" aria-hidden="true" />
            {suggestions.length} ứng viên
          </dd>
        </div>
      </dl>
    </article>
  );
}
