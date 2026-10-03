import { useCallback, useEffect, useState } from "react";
import Days from "./Days";
import Review from "./Review";

const dayFromUrl = () => new URLSearchParams(location.search).get("day");

// Two pages, and the address bar says which: no ?day is the day list, ?day=<key>
// is that day's grid. Kept in the URL so reload and the back button both work.
export default function App() {
  const [day, setDay] = useState<string | null>(dayFromUrl);

  useEffect(() => {
    const onPop = () => setDay(dayFromUrl());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const go = useCallback((key: string | null) => {
    history.pushState(null, "", key ? `?day=${encodeURIComponent(key)}` : location.pathname);
    setDay(key);
  }, []);

  return day ? <Review key={day} day={day} onBack={() => go(null)} /> : <Days onOpen={go} />;
}
