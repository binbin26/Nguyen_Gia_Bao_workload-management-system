const DEPARTMENTS = ["A", "B", "C"];

const STATUS_STYLES = {
  "Sẵn sàng": {
    bar: "bg-green-500",
    badge: "bg-green-50 text-green-700 ring-green-100",
  },
  "Bận": {
    bar: "bg-yellow-500",
    badge: "bg-yellow-50 text-yellow-800 ring-yellow-100",
  },
  "Quá tải": {
    bar: "bg-red-500 animate-pulse",
    badge: "bg-red-50 text-red-700 ring-red-100",
  },
  "Nghỉ phép": {
    bar: "bg-gray-300",
    badge: "bg-gray-100 text-gray-600 ring-gray-200",
  },
};

function clampPercent(value) {
  if (!Number.isFinite(value)) {
    return 0;
  }

  return Math.max(0, Math.min(100, value));
}

function getPercent(staff) {
  const currentHours = Number(staff?.workload_caps?.current_daily_hours || 0);
  const maxHours = Number(staff?.workload_caps?.max_daily_hours || 0);

  if (maxHours <= 0) {
    return 0;
  }

  return clampPercent((currentHours / maxHours) * 100);
}

function groupByDepartment(staffs) {
  return staffs.reduce(
    (groups, staff) => {
      const department = DEPARTMENTS.includes(staff.department)
        ? staff.department
        : "Khác";
      return {
        ...groups,
        [department]: [...(groups[department] || []), staff],
      };
    },
    { A: [], B: [], C: [] },
  );
}

function StaffRow({ staff }) {
  const percent = getPercent(staff);
  const caps = staff.workload_caps || {};
  const styles = STATUS_STYLES[staff.status] || STATUS_STYLES["Nghỉ phép"];
  const isOnLeave = staff.status === "Nghỉ phép";

  return (
    <article
      className={`rounded-md border border-slate-200 bg-white px-4 py-3 ${isOnLeave ? "opacity-70" : ""}`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-slate-950">
            {staff.fullname}
          </h3>
          <p className="mt-1 text-xs text-slate-500">{staff.id || staff._id}</p>
        </div>
        <span
          className={`inline-flex w-fit items-center rounded-md px-2.5 py-1 text-xs font-semibold ring-1 ${styles.badge}`}
        >
          {staff.status}
        </span>
      </div>

      <div className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-3 text-xs text-slate-500">
          <span>
            {Number(caps.current_daily_hours || 0).toFixed(1)}h /{" "}
            {Number(caps.max_daily_hours || 0).toFixed(1)}h
          </span>
          <span>{Math.round(percent)}%</span>
        </div>
        <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full rounded-full transition-all duration-500 ${styles.bar}`}
            style={{ width: `${percent}%` }}
            aria-label={`Tải lượng ${Math.round(percent)}%`}
          />
        </div>
        <p className="mt-2 text-xs text-slate-500">
          {Number(caps.current_daily_tasks || 0)} /{" "}
          {Number(caps.max_daily_tasks || 0)} tác vụ hôm nay
        </p>
      </div>
    </article>
  );
}

export default function WorkloadHeatmap({ staffs }) {
  const groupedStaffs = groupByDepartment(staffs);
  const departmentKeys = Object.keys(groupedStaffs);

  return (
    <section className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-lg font-semibold text-slate-950">
            Bản đồ tải lượng nhân sự
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            Theo dõi số giờ xử lý trong ngày theo từng phòng ban.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs font-medium">
          <span className="rounded-md bg-green-50 px-2.5 py-1 text-green-700 ring-1 ring-green-100">
            Sẵn sàng
          </span>
          <span className="rounded-md bg-yellow-50 px-2.5 py-1 text-yellow-800 ring-1 ring-yellow-100">
            Bận
          </span>
          <span className="rounded-md bg-red-50 px-2.5 py-1 text-red-700 ring-1 ring-red-100">
            Quá tải
          </span>
          <span className="rounded-md bg-gray-100 px-2.5 py-1 text-gray-600 ring-1 ring-gray-200">
            Nghỉ phép
          </span>
        </div>
      </div>

      <div className="grid gap-4 xl:grid-cols-3">
        {departmentKeys.map((department) => (
          <section
            key={department}
            className="rounded-lg border border-slate-200 bg-slate-50 p-4"
          >
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">
                  Phòng ban {department}
                </h3>
                <p className="mt-1 text-xs text-slate-500">
                  {groupedStaffs[department].length} nhân sự
                </p>
              </div>
              <span className="rounded-md bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 ring-1 ring-slate-200">
                Dept {department}
              </span>
            </div>

            <div className="space-y-3">
              {groupedStaffs[department].length > 0 ? (
                groupedStaffs[department].map((staff) => (
                  <StaffRow key={staff.id || staff._id} staff={staff} />
                ))
              ) : (
                <div className="rounded-md border border-dashed border-slate-300 bg-white px-4 py-8 text-center text-sm text-slate-500">
                  Chưa có dữ liệu nhân sự
                </div>
              )}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}
