import { AlertTriangle, Bot, RefreshCw, ShieldCheck } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import AIResolutionModal from "../components/analytics/AIResolutionModal";
import OverloadCard from "../components/analytics/OverloadCard";
import {
  OVERLOAD_ALERTS_QUERY_KEY,
  applyCapacitySuggestion,
  getOverloadAlerts,
  resolveOverloadAlert,
} from "../services/analytics_api";

function alertIdOf(alert) {
  return alert?.id || alert?._id || alert?.log_id || "";
}

function isPendingAlert(alert) {
  const action = alert?.manager_action?.action_taken || alert?.action_taken;
  return !action || action === "Pending";
}

function getEligibleSuggestionCount(alert) {
  const rawSuggestions = alert?.suggestions || alert?.ai_suggestions || [];

  if (!Array.isArray(rawSuggestions)) {
    return 0;
  }

  return rawSuggestions.filter((candidate) => {
    const score = Number(candidate?.matching_score || 0);
    return candidate?.status !== "Nghỉ phép" && score > 0;
  }).length;
}

function getErrorMessage(error, fallback) {
  return error?.response?.data?.message || error?.message || fallback;
}

export default function OverloadAlerts() {
  const queryClient = useQueryClient();
  const {
    data: alerts = [],
    error: alertsError,
    isPending: isLoading,
    isFetching,
    refetch,
  } = useQuery({
    queryKey: OVERLOAD_ALERTS_QUERY_KEY,
    queryFn: getOverloadAlerts,
  });

  const [selectedAlert, setSelectedAlert] = useState(null);
  const [resolvingStaffId, setResolvingStaffId] = useState("");
  const [modalError, setModalError] = useState("");
  const [toast, setToast] = useState(null);

  const error = alertsError
    ? getErrorMessage(
        alertsError,
        "Không thể tải danh sách cảnh báo quá tải. Vui lòng thử lại.",
      )
    : "";

  useEffect(() => {
    if (!toast) {
      return undefined;
    }

    const timerId = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timerId);
  }, [toast]);

  const pendingAlerts = useMemo(
    () => alerts.filter(isPendingAlert),
    [alerts],
  );

  const handleOpenModal = (alert) => {
    setModalError("");
    setSelectedAlert(alert);
  };

  const handleCloseModal = () => {
    if (resolvingStaffId) {
      return;
    }

    setModalError("");
    setSelectedAlert(null);
  };

  const handleApprove = async (logId, selectedStaffId) => {
    const isCapacityAlert = selectedAlert?.alert_type === "staff_capacity";
    const sourceStaffId = selectedAlert?.staff_id || "";

    if (
      !selectedStaffId ||
      (isCapacityAlert ? !sourceStaffId : !logId)
    ) {
      setModalError("Không xác định được cảnh báo hoặc nhân sự cần điều chuyển.");
      return;
    }

    setResolvingStaffId(selectedStaffId);
    setModalError("");

    try {
      if (isCapacityAlert) {
        await applyCapacitySuggestion(sourceStaffId, selectedStaffId);
      } else {
        await resolveOverloadAlert(logId, selectedStaffId);
      }
      await queryClient.invalidateQueries(
        {
          queryKey: OVERLOAD_ALERTS_QUERY_KEY,
          exact: true,
        },
        {
          cancelRefetch: false,
        },
      );
      setSelectedAlert(null);
      setToast({
        type: "success",
        message: isCapacityAlert
          ? "Đã áp dụng gợi ý cân bằng tải thành công!"
          : "Đã luân chuyển hồ sơ thành công!",
      });
    } catch (err) {
      setModalError(
        getErrorMessage(
          err,
          "Không thể phê duyệt điều chuyển. Vui lòng thử lại.",
        ),
      );
    } finally {
      setResolvingStaffId("");
    }
  };

  return (
    <>
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-amber-700">
            Trung tâm cảnh báo chủ động
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">
            Cảnh báo hệ thống
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Theo dõi các hồ sơ đang nghẽn tải và dùng gợi ý AI để điều phối
            nhân sự thay thế theo Matching Score.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void refetch()}
          disabled={isFetching}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            className={`h-4 w-4 ${isFetching ? "animate-spin" : ""}`}
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

      <section className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-amber-50 text-amber-700">
              <AlertTriangle className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Đang chờ xử lý</p>
              <p className="text-2xl font-semibold text-slate-950">
                {isLoading ? "..." : pendingAlerts.length}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
              <Bot className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Gợi ý AI</p>
              <p className="text-2xl font-semibold text-slate-950">
                {isLoading
                  ? "..."
                  : pendingAlerts.reduce(
                      (total, alert) =>
                        total + getEligibleSuggestionCount(alert),
                      0,
                    )}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-sky-50 text-sky-700">
              <ShieldCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Resolve API</p>
              <p className="text-2xl font-semibold text-slate-950">Live</p>
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-4">
        {isLoading ? (
          ["skeleton-1", "skeleton-2", "skeleton-3"].map((item) => (
            <div
              key={item}
              className="h-44 animate-pulse rounded-lg border border-amber-100 bg-amber-50"
            />
          ))
        ) : pendingAlerts.length > 0 ? (
          pendingAlerts.map((alert) => (
            <OverloadCard
              key={alertIdOf(alert)}
              alert={alert}
              onResolve={handleOpenModal}
            />
          ))
        ) : (
          <div className="rounded-lg border border-dashed border-slate-300 bg-white px-4 py-12 text-center">
            <ShieldCheck
              className="mx-auto h-10 w-10 text-emerald-500"
              aria-hidden="true"
            />
            <p className="mt-3 text-sm font-semibold text-slate-700">
              Không có cảnh báo pending
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Tải lượng hiện tại chưa cần can thiệp điều phối.
            </p>
          </div>
        )}
      </section>

      <AIResolutionModal
        alert={selectedAlert}
        isOpen={Boolean(selectedAlert)}
        onClose={handleCloseModal}
        onApprove={handleApprove}
        resolvingStaffId={resolvingStaffId}
        error={modalError}
      />

      {toast ? (
        <div
          className={`fixed bottom-5 right-5 z-[60] max-w-sm rounded-lg border px-4 py-3 text-sm font-medium shadow-lg ${
            toast.type === "success"
              ? "border-emerald-200 bg-emerald-50 text-emerald-700"
              : "border-red-200 bg-red-50 text-red-700"
          }`}
          role="status"
        >
          {toast.message}
        </div>
      ) : null}
    </>
  );
}
