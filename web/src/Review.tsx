import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RowsPhotoAlbum } from "react-photo-album";
import Lightbox from "yet-another-react-lightbox";
import Zoom from "yet-another-react-lightbox/plugins/zoom";
import Counter from "yet-another-react-lightbox/plugins/counter";
import "yet-another-react-lightbox/plugins/counter.css";
import { decide, loadShoot, saveGroups, type Frame, type Patch, type Shoot } from "./api";

type Filter =
  | { kind: "all" }
  | { kind: "undecided" }
  | { kind: "keep" }
  | { kind: "reject" }
  | { kind: "favourite" }
  | { kind: "rated"; min: number }
  | { kind: "group"; name: string }
  | { kind: "ungrouped" };

const isDecided = (f: Frame) => !!(f.reject || f.keep || f.rating || f.favourite || f.group);

function matches(f: Frame, filter: Filter): boolean {
  switch (filter.kind) {
    case "all": return true;
    case "undecided": return !isDecided(f);
    case "keep": return !f.reject;
    case "reject": return !!f.reject;
    case "favourite": return !!f.favourite;
    case "rated": return (f.rating ?? 0) >= filter.min;
    case "group": return f.group === filter.name;
    case "ungrouped": return !f.group && !f.reject;
  }
}

function timeOf(f: Frame) {
  return f.captured ? f.captured.slice(11, 19) : "";
}

export default function Review({ day, onBack }: { day: string; onBack: () => void }) {
  const [shoot, setShoot] = useState<Shoot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilterState] = useState<Filter>({ kind: "all" });
  const [focus, setFocus] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [anchor, setAnchor] = useState<number | null>(null);
  const [lightbox, setLightbox] = useState(false);
  const [picker, setPicker] = useState(false);
  const [help, setHelp] = useState(false);
  const gridRef = useRef<HTMLDivElement>(null);

  // A selection made under one filter must not follow into the next, where
  // some of it may be out of sight.
  const setFilter = useCallback((f: Filter) => {
    setFilterState(f);
    setSelected(new Set());
    setAnchor(null);
  }, []);

  useEffect(() => {
    loadShoot(day)
      .then((s) => {
        setShoot(s);
        // ?frame=<id> deep-links straight into the lightbox on that frame.
        const want = new URLSearchParams(location.search).get("frame");
        const i = want ? s.frames.findIndex((f) => f.id === want) : -1;
        if (i >= 0) { setFocus(i); setLightbox(true); }
      })
      .catch((e) => setError(String(e)));
  }, [day]);

  const visible = useMemo(
    () => (shoot ? shoot.frames.filter((f) => matches(f, filter)) : []),
    [shoot, filter]
  );

  // Keep focus inside the visible set when the filter shrinks it.
  useEffect(() => {
    if (focus >= visible.length) setFocus(Math.max(0, visible.length - 1));
  }, [visible.length, focus]);

  // A decision can take frames out of the current filter; they leave the
  // selection with it, so no key ever lands on a frame that is not on screen.
  useEffect(() => {
    setSelected((s) => {
      if (!s.size) return s;
      const ids = new Set(visible.map((f) => f.id));
      const kept = [...s].filter((id) => ids.has(id));
      return kept.length === s.size ? s : new Set(kept);
    });
  }, [visible]);

  useEffect(() => {
    const el = gridRef.current?.querySelector<HTMLElement>(`[data-index="${focus}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [focus, visible]);

  // ---- decisions -------------------------------------------------------

  const targets = useCallback((): string[] => {
    const f = visible[focus];
    // Full size shows one frame, so that is the one a key applies to.
    if (lightbox) return f ? [f.id] : [];
    if (selected.size) return [...selected];
    return f ? [f.id] : [];
  }, [selected, visible, focus, lightbox]);

  const apply = useCallback(
    (ids: string[], patch: Patch) => {
      if (!ids.length || !shoot) return;
      setShoot((s) => {
        if (!s) return s;
        const groups = patch.group && !s.groups.includes(patch.group) ? [...s.groups, patch.group] : s.groups;
        return {
          ...s,
          groups,
          frames: s.frames.map((f) => (ids.includes(f.id) ? { ...f, ...patch } : f)),
        };
      });
      decide(day, ids, patch).catch((e) => setError(`save failed: ${e}`));
    },
    [shoot, day]
  );

  // After a verdict on a single frame, step to the next one so culling is one
  // key per frame. Not for a multi-select, and not when the verdict takes the
  // frame out of the current filter: then the next frame slides into its place.
  const advance = useCallback(
    (patch: Patch) => {
      const f = visible[focus];
      if (!f || (selected.size && !lightbox)) return;
      if (matches({ ...f, ...patch }, filter)) setFocus(Math.min(visible.length - 1, focus + 1));
    },
    [visible, focus, selected, lightbox, filter]
  );

  const toggle = useCallback(
    (key: "reject" | "keep" | "favourite") => {
      const ids = targets();
      const first = shoot?.frames.find((f) => f.id === ids[0]);
      const patch: Patch = { [key]: !first?.[key] };
      // Keep and reject are the two answers to one question.
      if (key === "reject") patch.keep = false;
      if (key === "keep") patch.reject = false;
      apply(ids, patch);
      // Favourite is an extra on top of a verdict, and un-doing one is a
      // correction; neither means "done with this frame".
      if (key !== "favourite" && patch[key]) advance(patch);
    },
    [targets, shoot, apply, advance]
  );

  const rate = useCallback(
    (n: number) => {
      const ids = targets();
      const first = shoot?.frames.find((f) => f.id === ids[0]);
      // Pressing the current rating again clears it.
      const patch: Patch = { rating: first?.rating === n ? 0 : n };
      apply(ids, patch);
      if (patch.rating) advance(patch);
    },
    [targets, shoot, apply, advance]
  );

  // The usual way to finish a day: reject the duds, then keep everything else.
  const keepRest = useCallback(() => {
    if (!shoot) return;
    apply(shoot.frames.filter((f) => !isDecided(f)).map((f) => f.id), { keep: true });
  }, [shoot, apply]);

  const assignGroup = useCallback(
    (name: string | null) => {
      apply(targets(), { group: name ?? "" });
      setPicker(false);
    },
    [apply, targets]
  );

  const removeGroup = useCallback(
    (name: string) => {
      if (!shoot) return;
      const ids = shoot.frames.filter((f) => f.group === name).map((f) => f.id);
      apply(ids, { group: "" });
      const groups = shoot.groups.filter((g) => g !== name);
      setShoot((s) => (s ? { ...s, groups } : s));
      saveGroups(day, groups).catch((e) => setError(`save failed: ${e}`));
      if (filter.kind === "group" && filter.name === name) setFilter({ kind: "all" });
    },
    [shoot, apply, filter, day, setFilter]
  );

  // ---- navigation ------------------------------------------------------

  const move = useCallback(
    (delta: number, extend: boolean, vertical = false) => {
      if (!visible.length) return;
      let next = focus;
      if (vertical) {
        // Justified rows have no fixed column count; find the tile in the
        // adjacent row whose centre is nearest horizontally.
        const tiles = [...(gridRef.current?.querySelectorAll<HTMLElement>("[data-index]") ?? [])];
        const cur = tiles[focus]?.getBoundingClientRect();
        if (!cur) return;
        const cx = cur.left + cur.width / 2;
        let best: { i: number; d: number } | null = null;
        tiles.forEach((t, i) => {
          const r = t.getBoundingClientRect();
          const below = r.top > cur.bottom - 1;
          const above = r.bottom < cur.top + 1;
          if (delta > 0 ? !below : !above) return;
          const rowGap = delta > 0 ? r.top - cur.bottom : cur.top - r.bottom;
          const d = rowGap * 10000 + Math.abs(r.left + r.width / 2 - cx);
          if (!best || d < best.d) best = { i, d };
        });
        if (!best) return;
        next = (best as { i: number }).i;
      } else {
        next = Math.min(visible.length - 1, Math.max(0, focus + delta));
      }
      if (extend) {
        const a = anchor ?? focus;
        const [lo, hi] = [Math.min(a, next), Math.max(a, next)];
        setSelected(new Set(visible.slice(lo, hi + 1).map((f) => f.id)));
        setAnchor(a);
      } else {
        // Moving on without shift lets go of the selection, as a plain click
        // does; otherwise the next key would act on frames left behind.
        setSelected(new Set());
        setAnchor(null);
      }
      setFocus(next);
    },
    [visible, focus, anchor]
  );

  const click = useCallback(
    (index: number, e: { shiftKey: boolean; ctrlKey: boolean; metaKey: boolean }) => {
      const id = visible[index].id;
      if (e.shiftKey) {
        const a = anchor ?? focus;
        const [lo, hi] = [Math.min(a, index), Math.max(a, index)];
        const range = visible.slice(lo, hi + 1).map((f) => f.id);
        setSelected((s) => (e.ctrlKey || e.metaKey ? new Set([...s, ...range]) : new Set(range)));
        setAnchor(a);
      } else if (e.ctrlKey || e.metaKey) {
        setSelected((s) => {
          const n = new Set(s);
          n.has(id) ? n.delete(id) : n.add(id);
          return n;
        });
        setAnchor(index);
      } else {
        setSelected(new Set());
        setAnchor(index);
      }
      setFocus(index);
    },
    [visible, anchor, focus]
  );

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA")) return;
      if (picker || help) {
        if (e.key === "Escape") { setPicker(false); setHelp(false); e.preventDefault(); }
        return;
      }
      const k = e.key;
      const stop = () => e.preventDefault();
      // Ctrl-F, ctrl-1 and the rest belong to the browser; only select-all is ours.
      if (e.ctrlKey || e.metaKey || e.altKey) {
        if (k === "a" && !e.altKey && !lightbox) { setSelected(new Set(visible.map((f) => f.id))); stop(); }
        return;
      }
      // With the lightbox open the arrows are its own; it reports the new
      // index through the `view` callback, which keeps focus in step.
      if (k.startsWith("Arrow") && lightbox) return;
      if (k === "ArrowRight") { move(1, e.shiftKey); stop(); }
      else if (k === "ArrowLeft") { move(-1, e.shiftKey); stop(); }
      else if (k === "ArrowDown") { move(1, e.shiftKey, true); stop(); }
      else if (k === "ArrowUp") { move(-1, e.shiftKey, true); stop(); }
      else if (k === " " || k === "Enter") { setLightbox((v) => !v); stop(); }
      else if (k === "x" || k === "X") { toggle("reject"); stop(); }
      else if (k === "k" || k === "K") { toggle("keep"); stop(); }
      else if (k === "f" || k === "F") { toggle("favourite"); stop(); }
      else if (k >= "1" && k <= "5") { rate(Number(k)); stop(); }
      else if (k === "0" || k === "u" || k === "U") { apply(targets(), { rating: 0, reject: false, keep: false, favourite: false, group: "" }); stop(); }
      else if (k === "g" || k === "G") { setPicker(true); stop(); }
      else if (k === "Escape") {
        // Esc backs out one level at a time: full size, selection, then the day.
        if (lightbox) setLightbox(false);
        else if (selected.size) setSelected(new Set());
        else onBack();
        stop();
      }
      else if (k === "?") { setHelp(true); stop(); }
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [move, toggle, rate, apply, targets, picker, help, lightbox, visible, selected, onBack]);

  // ---- render ----------------------------------------------------------

  if (error && !shoot) return <div className="empty">{error}</div>;
  if (!shoot) return <div className="empty">preparing {day}… (thumbnails are rendered the first time a day is opened)</div>;

  const counts = {
    total: shoot.frames.length,
    reject: shoot.frames.filter((f) => f.reject).length,
    fav: shoot.frames.filter((f) => f.favourite).length,
    undecided: shoot.frames.filter((f) => !isDecided(f)).length,
  };
  const groupCounts = new Map(shoot.groups.map((g) => [g, shoot.frames.filter((f) => f.group === g).length]));

  const chip = (label: string, f: Filter, n?: number) => {
    const active = JSON.stringify(f) === JSON.stringify(filter);
    return (
      <button key={label} className={"chip" + (active ? " active" : "")} onClick={() => setFilter(f)}>
        {label}
        {n !== undefined && <span className="n">{n}</span>}
      </button>
    );
  };

  const photos = visible.map((f) => ({ src: f.thumb, width: f.width, height: f.height, key: f.id, frame: f }));

  return (
    <div className="app">
      <header>
        <button className="chip" onClick={onBack}>← days</button>
        <div className="title">
          <strong>{shoot.name}</strong>
          <span className="muted">{shoot.path}</span>
        </div>
        <div className="chips">
          {chip("All", { kind: "all" }, counts.total)}
          {chip("Undecided", { kind: "undecided" }, counts.undecided)}
          {chip("Keep", { kind: "keep" }, counts.total - counts.reject)}
          {chip("Rejected", { kind: "reject" }, counts.reject)}
          {chip("★ 3+", { kind: "rated", min: 3 })}
          {chip("♥", { kind: "favourite" }, counts.fav)}
          {chip("Ungrouped", { kind: "ungrouped" })}
          {counts.undecided ? (
            <button className="chip action" title="mark every undecided frame as a keep" onClick={keepRest}>
              ✓ Keep the rest<span className="n">{counts.undecided}</span>
            </button>
          ) : null}
        </div>
        <div className="status">
          {selected.size ? <span className="sel">{selected.size} selected</span> : null}
          <span className="muted">{counts.total - counts.undecided} of {counts.total} decided</span>
          {error ? <span className="err">{error}</span> : null}
          <button className="chip" onClick={() => setHelp(true)}>?</button>
        </div>
      </header>

      <div className="body">
        <main ref={gridRef}>
          {visible.length === 0 ? (
            <div className="empty">nothing matches this filter</div>
          ) : (
            <RowsPhotoAlbum
              photos={photos}
              targetRowHeight={220}
              spacing={6}
              onClick={({ index, event }) => click(index, event)}
              render={{
                // With onClick set the album renders each photo as a
                // <button>, so that is where the tile classes must go.
                button: (props, { index, photo }) => {
                  const f = photo.frame;
                  const cls = [
                    props.className ?? "",
                    "tile",
                    index === focus ? "focus" : "",
                    selected.has(f.id) ? "selected" : "",
                    f.reject ? "rejected" : "",
                  ].join(" ");
                  return (
                    <button
                      {...props}
                      className={cls}
                      data-index={index}
                      onDoubleClick={() => { setFocus(index); setLightbox(true); }}
                    />
                  );
                },
                extras: (_, { photo }) => {
                  const f = photo.frame;
                  return (
                    <div className="badges">
                      {f.reject && <div className="veto">✕</div>}
                      <div className="top">
                        {f.keep && <span className="keep">✓</span>}
                        {f.favourite && <span className="fav">♥</span>}
                        {f.raw && <span className="raw">RAW</span>}
                      </div>
                      <div className="bottom">
                        <span className="time">{timeOf(f)}</span>
                        {f.rating ? <span className="stars">{"★".repeat(f.rating)}</span> : null}
                        {f.group && <span className="group">{f.group}</span>}
                      </div>
                    </div>
                  );
                },
              }}
            />
          )}
        </main>

        <aside>
          <h3>Groups</h3>
          {shoot.groups.length === 0 && <p className="muted">Press <kbd>g</kbd> on a frame to start one.</p>}
          <ul className="groups">
            {shoot.groups.map((g) => (
              <li key={g} className={filter.kind === "group" && filter.name === g ? "active" : ""}>
                <button className="name" onClick={() => setFilter({ kind: "group", name: g })}>
                  {g} <span className="n">{groupCounts.get(g)}</span>
                </button>
                <button className="assign" title="assign selection to this group" onClick={() => assignGroup(g)}>+</button>
                <button className="del" title="remove group" onClick={() => removeGroup(g)}>×</button>
              </li>
            ))}
          </ul>
          <h3>Keys</h3>
          <dl className="keys">
            <dt>←→↑↓</dt><dd>move (shift: select range)</dd>
            <dt>space</dt><dd>full size</dd>
            <dt>x</dt><dd>reject</dd>
            <dt>k</dt><dd>keep</dd>
            <dt>1–5</dt><dd>rate</dd>
            <dt>f</dt><dd>favourite</dd>
            <dt>g</dt><dd>group</dd>
            <dt>0</dt><dd>clear everything</dd>
            <dt>ctrl-a</dt><dd>select all shown</dd>
            <dt>ctrl-click</dt><dd>toggle select</dd>
            <dt>esc</dt><dd>deselect, then back to days</dd>
          </dl>
        </aside>
      </div>

      <Lightbox
        open={lightbox}
        close={() => setLightbox(false)}
        index={focus}
        slides={visible.map((f) => ({ src: f.web, width: f.width * 8, height: f.height * 8, frame: f }))}
        on={{ view: ({ index }) => setFocus(index) }}
        plugins={[Zoom, Counter]}
        carousel={{ finite: true, preload: 2 }}
        animation={{ fade: 150, swipe: 200 }}
        controller={{ closeOnBackdropClick: true }}
        zoom={{ maxZoomPixelRatio: 2 }}
        render={{
          slideFooter: ({ slide }) => {
            const f = (slide as { frame?: Frame }).frame;
            if (!f) return null;
            return (
              <div className="lb-footer">
                <span>{f.id}</span>
                {f.rating ? <span className="stars">{"★".repeat(f.rating)}</span> : null}
                {f.favourite && <span className="fav">♥</span>}
                {f.keep && <span className="keep">kept</span>}
                {f.reject && <span className="x">rejected</span>}
                {f.group && <span className="group">{f.group}</span>}
              </div>
            );
          },
        }}
      />

      {picker && (
        <GroupPicker
          groups={shoot.groups}
          count={targets().length}
          onPick={assignGroup}
          onClose={() => setPicker(false)}
        />
      )}

      {help && (
        <div className="overlay" onClick={() => setHelp(false)}>
          <div className="dialog">
            <h2>Review</h2>
            <p>Arrow keys move the focus; hold shift to select a range, or ctrl-click. Every decision key applies to the selection, or to the focused frame if nothing is selected. At full size it applies to the frame on screen.</p>
            <p><kbd>x</kbd> reject &nbsp; <kbd>k</kbd> keep &nbsp; <kbd>1</kbd>–<kbd>5</kbd> rate &nbsp; <kbd>f</kbd> favourite &nbsp; <kbd>g</kbd> group &nbsp; <kbd>0</kbd> clear every decision &nbsp; <kbd>ctrl-a</kbd> select all shown &nbsp; <kbd>?</kbd> this help &nbsp; <kbd>space</kbd> full size &nbsp; <kbd>esc</kbd> back (full size, selection, then the day list)</p>
            <p className="muted">Decisions are written to review.json in the day folder as you go.</p>
          </div>
        </div>
      )}
    </div>
  );
}

function GroupPicker({
  groups, count, onPick, onClose,
}: { groups: string[]; count: number; onPick: (g: string | null) => void; onClose: () => void }) {
  const [text, setText] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => input.current?.focus(), []);
  const matchesText = groups.filter((g) => g.toLowerCase().includes(text.toLowerCase()));

  return (
    <div className="overlay" onClick={onClose}>
      <div className="dialog picker" onClick={(e) => e.stopPropagation()}>
        <h2>Group {count} frame{count === 1 ? "" : "s"}</h2>
        <input
          ref={input}
          value={text}
          placeholder="new or existing group name"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && text.trim()) onPick(text.trim());
            else if (e.key === "Escape") onClose();
            else if (e.key >= "1" && e.key <= "9" && !text) {
              const g = groups[Number(e.key) - 1];
              if (g) onPick(g);
            }
          }}
        />
        <ul>
          {matchesText.map((g, i) => (
            <li key={g}><button onClick={() => onPick(g)}><kbd>{i + 1}</kbd> {g}</button></li>
          ))}
          {text.trim() && !groups.includes(text.trim()) && (
            <li><button onClick={() => onPick(text.trim())}>create “{text.trim()}”</button></li>
          )}
          <li><button className="muted" onClick={() => onPick(null)}>no group</button></li>
        </ul>
      </div>
    </div>
  );
}
