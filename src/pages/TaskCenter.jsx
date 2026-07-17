import { RefreshCw, Route, SearchCheck } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import TaskDetailDrawer from "../components/tasks/TaskDetailDrawer";
import TaskFilter from "../components/tasks/TaskFilter";
import TaskTable from "../components/tasks/TaskTable";
import { getTasks, nextStepTask } from "../services/task_api";

const DEFAULT_FILTERS = {
  status: "Tất cả",
  department: "Tất cả",
};

function taskIdOf(task) {
  return task?.id || task?._id || "";
}

function getErrorMessage(error, fallback) {
  return error?.response?.data?.message || error?.message || fallback;
}

export default function TaskCenter() {
  const [tasks, setTasks] = useState([]);
  const [filters, setFilters] = useState(DEFAULT_FILTERS);
  const [selectedTask, setSelectedTask] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [advancingTaskId, setAdvancingTaskId] = useState("");
  const [error, setError] = useState("");
  const [toast, setToast] = useState(null);

  const loadTasks = async () => {
    setIsLoading(true);
    setError("");

    try {
      const data = await getTasks();
      setTasks(data);
    } catch (err) {
      setError(
        getErrorMessage(err, "Không thể tải danh sách hồ sơ. Vui lòng thử lại."),
      );
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadTasks();
  }, []);

  useEffect(() => {
    if (!toast) {
      return undefined;
    }

    const timerId = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(timerId);
  }, [toast]);

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      const matchStatus =
        filters.status === "Tất cả" || task.status === filters.status;
      const matchDepartment =
        filters.department === "Tất cả" ||
        task.current_department === filters.department;

      return matchStatus && matchDepartment;
    });
  }, [filters, tasks]);

  const handleNextStep = async (task) => {
    const taskId = taskIdOf(task);
    if (!taskId) {
      setToast({
        type: "error",
        message: "Không xác định được mã định danh hồ sơ.",
      });
      return;
    }

    setAdvancingTaskId(taskId);

    try {
      await nextStepTask(taskId);
      setSelectedTask(null);
      setToast({
        type: "success",
        message: "Luân chuyển bước thành công.",
      });
      await loadTasks();
    } catch (err) {
      setToast({
        type: "error",
        message: getErrorMessage(err, "Không thể luân chuyển hồ sơ."),
      });
    } finally {
      setAdvancingTaskId("");
    }
  };

  return (
    <>
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-sm font-medium text-sky-700">
            Điều phối state machine
          </p>
          <h1 className="mt-2 text-2xl font-semibold tracking-normal text-slate-950">
            Trung tâm quản lý hồ sơ
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
            Theo dõi trạng thái, phòng ban xử lý và tiến trình từng bước của
            toàn bộ hồ sơ.
          </p>
        </div>

        <button
          type="button"
          onClick={loadTasks}
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

      <section className="grid gap-4 sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-sky-50 text-sky-700">
              <SearchCheck className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Đang hiển thị</p>
              <p className="text-2xl font-semibold text-slate-950">
                {isLoading ? "..." : filteredTasks.length}
              </p>
            </div>
          </div>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
              <Route className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-medium text-slate-500">Tổng hồ sơ</p>
              <p className="text-2xl font-semibold text-slate-950">
                {isLoading ? "..." : tasks.length}
              </p>
            </div>
          </div>
        </div>
      </section>

      <TaskFilter
        filters={filters}
        onChange={setFilters}
        onReset={() => setFilters(DEFAULT_FILTERS)}
      />

      <TaskTable
        tasks={filteredTasks}
        isLoading={isLoading}
        onSelectTask={setSelectedTask}
      />

      <TaskDetailDrawer
        task={selectedTask}
        isOpen={Boolean(selectedTask)}
        isAdvancing={advancingTaskId === taskIdOf(selectedTask)}
        onClose={() => setSelectedTask(null)}
        onNextStep={handleNextStep}
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
