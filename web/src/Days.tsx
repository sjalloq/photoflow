import { useEffect, useMemo, useRef, useState } from "react";
import { loadDays, type Day, type Days as DaysData } from "./api";

type SortKey = "status" | "date" | "ingested" | "progress" | "total";

const SORTS: { key: SortKey; label: string }[] = [
  { key: "status", label: "Needs review first" },
  { key: "date", label: "Capture date" },
  { key: "ingested", label: "Ingest date" },
  { key: "progress", label: "Review %" },
  { key: "total", label: "Frames" },
];

const progress = (d: Day) => (d.total ? d.decided / d.total : 0);

type Status = "new" | "started" | "reviewed";

function statusOf(d: Day, doneAt: number): Status {
  if (!d.decided) return "new";
  return progress(d) >= doneAt ? "reviewed" : "started";
}

const STATUS_LABEL: Record<Status, string> = { new: "New", started: "In progress", reviewed: "Reviewed" };
const STATUS_ORDER: Record<Status, number> = { started: 0, new: 1, reviewed: 2 };

function compare(a: Day, b: Day, key: SortKey, doneAt: number): number {
  const byDate = (b.date ?? b.name).localeCompare(a.date ?? a.name);
  switch (key) {
    case "status":
      return STATUS_ORDER[statusOf(a, doneAt)] - STATUS_ORDER[statusOf(b, doneAt)] || byDate;
    case "date": return byDate;
    case "ingested": return b.ingested.localeCompare(a.ingested) || byDate;
    case "progress": return progress(a) - progress(b) || byDate;
    case "total": return b.total - a.total || byDate;
  }
}

export default function Days({ onOpen }: { onOpen: (key: string) => void }) {
  const [data, setData] = useState<DaysData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sort, setSort] = useState<SortKey>(() => {
    try { return (localStorage.getItem("days.sort") as SortKey) || "status"; } catch { return "status"; }
  });
  const [reverse, setReverse] = useState(false);

  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const poll = () => {
      loadDays()
        .then((d) => {
          if (!alive) return;
          setData(d);
          setError(null);
          // Covers appear as the server's background render gets to each day,
          // so keep asking until every day has its thumbnails.
          if (d.days.some((x) => x.rendered < x.total)) timer = window.setTimeout(poll, 3000);
        })
        .catch((e) => alive && setError(String(e)));
    };
    poll();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);

  const days = useMemo(() => {
    if (!data) return [];
    const sorted = [...data.days].sort((a, b) => compare(a, b, sort, data.done_at));
    return reverse ? sorted.reverse() : sorted;
  }, [data, sort, reverse]);

  // Keyboard: the first day takes focus so Enter opens it, and the arrows walk
  // the cards, so a review can be driven without the mouse end to end.
  const list = useRef<HTMLDivElement>(null);
  const ready = !!data;
  useEffect(() => {
    if (ready) list.current?.querySelector<HTMLElement>(".day")?.focus();
  }, [ready]);
  const onKey = (e: React.KeyboardEvent) => {
    const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    const cards = [...(list.current?.querySelectorAll<HTMLElement>(".day") ?? [])];
    const at = cards.indexOf(document.activeElement as HTMLElement);
    cards[Math.min(cards.length - 1, Math.max(0, at + step))]?.focus();
    e.preventDefault();
  };

  const choose = (key: SortKey) => {
    setSort(key);
    setReverse(false);
    try { localStorage.setItem("days.sort", key); } catch { /* private window */ }
  };

  if (error && !data) return <div className="empty">{error}</div>;
  if (!data) return <div className="empty">loading…</div>;

  return (
    <div className="app">
      <header>
        <div className="title">
          <strong>photoflow review</strong>
          <span className="muted">{data.root}</span>
        </div>
        <div className="status">
          {error ? <span className="err">{error}</span> : null}
          <label className="muted">
            Sort{" "}
            <select value={sort} onChange={(e) => choose(e.target.value as SortKey)}>
              {SORTS.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
            </select>
          </label>
          <button className="chip" title="reverse the order" onClick={() => setReverse((r) => !r)}>
            {reverse ? "↑" : "↓"}
          </button>
        </div>
      </header>

      <div className="days" ref={list} onKeyDown={onKey}>
        {days.map((d) => {
          const status = statusOf(d, data.done_at);
          const pct = Math.round(progress(d) * 100);
          return (
            <button key={d.key} className="day" onClick={() => onOpen(d.key)}>
              <div className="day-head">
                <strong>{d.name}</strong>
                <span className="muted">{d.key.includes("/") ? d.key.split("/")[0] : ""}</span>
                <span className={`state ${status}`}>{STATUS_LABEL[status]}</span>
              </div>
              <div className="covers">
                {d.covers.length
                  ? d.covers.map((src) => <img key={src} src={src} alt="" loading="lazy" />)
                  : <span className="muted">rendering thumbnails…</span>}
              </div>
              <div className="bar"><div style={{ width: `${pct}%` }} /></div>
              <div className="day-foot muted">
                <span>{d.total} frame{d.total === 1 ? "" : "s"}</span>
                <span>{d.decided} decided ({pct}%){d.rejected ? `, ${d.rejected} rejected` : ""}</span>
                <span>ingested {d.ingested.slice(0, 10)}</span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
