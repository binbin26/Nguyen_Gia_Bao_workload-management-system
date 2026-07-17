export default function StatWidget({
  title,
  value,
  description,
  icon: Icon,
  tone = "sky",
}) {
  const toneClasses = {
    sky: "bg-sky-50 text-sky-700 ring-sky-100",
    green: "bg-green-50 text-green-700 ring-green-100",
    red: "bg-red-50 text-red-700 ring-red-100",
    amber: "bg-amber-50 text-amber-700 ring-amber-100",
  };

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-sm font-medium text-slate-500">{title}</p>
          <p className="mt-3 text-3xl font-semibold tracking-normal text-slate-950">
            {value}
          </p>
        </div>
        {Icon ? (
          <div
            className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-md ring-1 ${toneClasses[tone] || toneClasses.sky}`}
          >
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
        ) : null}
      </div>
      {description ? (
        <p className="mt-3 text-sm leading-6 text-slate-500">{description}</p>
      ) : null}
    </section>
  );
}
