export type Frame = {
  id: string;
  thumb: string;
  web: string;
  width: number;
  height: number;
  captured: string | null;
  raw: boolean;
  reject?: boolean;
  keep?: boolean;
  rating?: number;
  favourite?: boolean;
  group?: string;
};

export type Shoot = {
  key: string;
  name: string;
  path: string;
  groups: string[];
  frames: Frame[];
};

export type Day = {
  key: string;
  name: string;
  path: string;
  date: string | null;
  ingested: string;
  total: number;
  decided: number;
  rejected: number;
  rendered: number;
  covers: string[];
};

export type Days = { root: string; done_at: number; days: Day[] };

export type Patch = Partial<Pick<Frame, "reject" | "keep" | "rating" | "favourite" | "group">>;

async function post(url: string, body: unknown): Promise<void> {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
}

export async function loadDays(): Promise<Days> {
  const r = await fetch("/api/days");
  if (!r.ok) throw new Error(`days: ${r.status}`);
  return r.json();
}

export async function loadShoot(day: string): Promise<Shoot> {
  const r = await fetch(`/api/shoot?day=${encodeURIComponent(day)}`);
  if (!r.ok) throw new Error(`shoot: ${r.status}`);
  return r.json();
}

export const decide = (day: string, ids: string[], patch: Patch) => post("/api/decide", { day, ids, patch });

export const saveGroups = (day: string, groups: string[]) => post("/api/groups", { day, groups });
