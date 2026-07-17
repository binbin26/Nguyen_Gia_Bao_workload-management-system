import { Bot, CheckCircle2, LoaderCircle, Sparkles, X } from "lucide-react";

function alertIdOf(alert) {
  return alert?.id || alert?._id || alert?.log_id || "";
}

function getSuggestions(alert) {
  const rawSuggestions = alert?.suggestions || alert?.ai_suggestions || [];

  if (!Array.isArray(rawSuggestions)) {
    return [];
  }

  return rawSuggestions
    .filter((candidate) => {
      const score = Number(candidate?.matching_score || 0);
      return candidate?.status !== "Nghỉ phép" && score > 0;
    })
    .sort(
      (left, right) =>
        Number(right?.matching_score || 0) - Number(left?.matching_score || 0),
    );
}

function staffIdOf(candidate) {
  return candidate?.staff_id || candidate?.id || candidate?._id || "";
}

function getPercent(candidate) {
  const score = Number(candidate?.matching_score || 0);
  const percent = score * 100;

  if (!Number.isFinite(percent)) {
    return 0;
  }

  return Math.max(0, Math.min(100, Math.round(percent)));
}

function getCandidateName(candidate) {
  return (
    candidate?.fullname ||
    candidate?.full_name ||
    candidate?.staff_name ||
    staffIdOf(candidate) ||
    "Nhân sự đề xuất"
  );
}

export default function AIResolutionModal({
  alert,
  isOpen,
  onClose,
  onApprove,
  resolvingStaffId,
  error,
}) {
  if (!isOpen || !alert) {
    return null;
  }

  const suggestions = getSuggestions(alert);
  const task = alert?.task || {};
  const isResolving = Boolean(resolvingStaffId);

  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        className="absolute inset-0 cursor-default bg-slate-950/45"
        onClick={isResolving ? undefined : onClose}
        aria-label="Đóng popup gợi ý AI"
      />

      <section className="absolute left-1/2 top-1/2 flex max-h-[92vh] w-[calc(100%-2rem)] max-w-4xl -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-lg bg-white shadow-2xl">
        <header className="border-b border-slate-200 bg-slate-950 px-5 py-4 text-white">
          <div className="flex items-start justify-between gap-4">
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-sm font-medium text-emerald-200">
                <Bot className="h-4 w-4" aria-hidden="true" />
                AI-powered Decision Support
              </p>
              <h2 className="mt-2 text-xl font-semibold tracking-normal">
                Gợi ý điều chuyển hồ sơ {task.task_code || task.task_id || ""}
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-300">
                matching_score = 1.0 - (current_daily_hours / max_daily_hours)
              </p>
            </div>
            <button
              type="button"
              onClick={onClose}
              disabled={isResolving}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-white/10 bg-white/5 text-slate-200 transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-50"
              aria-label="Đóng"
            >
              <X className="h-5 w-5" aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto bg-slate-50 px-5 py-5">
          {error ? (
            <div
              className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm font-medium text-red-700"
              role="alert"
            >
              {error}
            </div>
          ) : null}

          {suggestions.length > 0 ? (
            <div className="space-y-3">
              {suggestions.map((candidate, index) => {
                const staffId = staffIdOf(candidate);
                const percent = getPercent(candidate);
                const isBestMatch = index === 0;
                const isCurrentResolving = resolvingStaffId === staffId;

                return (
                  <article
                    key={staffId || `${getCandidateName(candidate)}-${index}`}
                    className={`rounded-lg border bg-white p-4 shadow-sm ${
                      isBestMatch
                        ? "border-emerald-300 ring-2 ring-emerald-100"
                        : "border-slate-200"
                    }`}
                  >
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-base font-semibold text-slate-950">
                            {getCandidateName(candidate)}
                          </h3>
                          {isBestMatch ? (
                            <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-100">
                              <Sparkles
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              />
                              Khuyên chọn
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm text-slate-500">
                          {staffId || "Chưa có mã"} · Phòng ban{" "}
                          {candidate?.department || task.current_department || "-"}
                        </p>

                        <div className="mt-4">
                          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                            <span className="text-xs font-medium text-slate-500">
                              ETC hiện tại:{" "}
                              {Number(
                                candidate?.current_daily_hours || 0,
                              ).toFixed(1)}
                              h
                              {candidate?.max_daily_hours
                                ? ` / ${Number(candidate.max_daily_hours).toFixed(1)}h`
                                : ""}
                            </span>
                            <span className="rounded-md bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-700 ring-1 ring-emerald-100">
                              {percent}% Phù hợp
                            </span>
                          </div>
                          <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                            <div
                              className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                              style={{ width: `${percent}%` }}
                              aria-label={`Độ phù hợp ${percent}%`}
                            />
                          </div>
                          <p className="mt-2 text-xs text-slate-500">
                            {Number(candidate?.current_daily_tasks || 0)} tác vụ
                            đang giữ hôm nay
                          </p>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => onApprove(alertIdOf(alert), staffId)}
                        disabled={!staffId || isResolving}
                        className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-md bg-emerald-600 px-4 text-sm font-semibold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
                      >
                        {isCurrentResolving ? (
                          <LoaderCircle
                            className="h-4 w-4 animate-spin"
                            aria-hidden="true"
                          />
                        ) : (
                          <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
                        )}
                        Phê duyệt điều chuyển
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
              <Bot className="mx-auto h-9 w-9 text-slate-400" aria-hidden="true" />
              <p className="mt-3 text-sm font-semibold text-slate-700">
                Chưa có ứng viên khả dụng
              </p>
              <p className="mt-1 text-sm text-slate-500">
                UI đã loại các ứng viên nghỉ phép hoặc có Matching Score không
                dương.
              </p>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
