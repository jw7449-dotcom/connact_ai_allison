"use client";
import {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  useCallback,
} from "react";
import { useRouter } from "next/navigation";
import { api, errorText } from "./api";
import type { Persona, Contact, Draft, Config } from "./types";

type State = {
  locale: string;
  t: (en: string, zh: string) => string;
  setLocale: (v: string) => void;
  personas: Persona[];
  contacts: Contact[];
  drafts: Draft[];
  config: Config | null;
  refresh: () => Promise<void>;
  notify: (s: string) => void;
  go: (s: string) => Promise<void>;
  guard: React.MutableRefObject<null | (() => Promise<unknown>)>;
  error: string;
  loading: boolean;
};
const Context = createContext<State>(null!);
export const useApp = () => useContext(Context);
export function AppProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState("en"),
    [personas, setPersonas] = useState<Persona[]>([]),
    [contacts, setContacts] = useState<Contact[]>([]),
    [drafts, setDrafts] = useState<Draft[]>([]),
    [config, setConfig] = useState<Config | null>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [toast, setToast] = useState("");
  const router = useRouter(),
    guard = useRef<null | (() => Promise<unknown>)>(null),
    toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    setLocaleState(localStorage.getItem("meridian-locale") || "en");
  }, []);
  const setLocale = (v: string) => {
    setLocaleState(v);
    localStorage.setItem("meridian-locale", v);
    document.documentElement.lang = v === "zh" ? "zh-CN" : "en";
  };
  const refresh = useCallback(async () => {
    try {
      const [p, c, d, cf] = await Promise.all([
        api<Persona[]>("/personas"),
        api<Contact[]>("/contacts"),
        api<Draft[]>("/drafts"),
        api<Config>("/config"),
      ]);
      setPersonas(p);
      setContacts(c);
      setDrafts(d);
      setConfig(cf);
      setError("");
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const notify = useCallback((s: string) => {
    setToast(s);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(""), 5500);
  }, []);
  const go = useCallback(
    async (path: string) => {
      try {
        if (guard.current) await guard.current();
        router.push(path);
      } catch (e) {
        notify(errorText(e));
      }
    },
    [router, notify],
  );
  return (
    <Context.Provider
      value={{
        locale,
        t: (a, b) => (locale === "zh" ? b : a),
        setLocale,
        personas,
        contacts,
        drafts,
        config,
        refresh,
        notify,
        go,
        guard,
        error,
        loading,
      }}
    >
      {children}
      {toast && (
        <div className="toast" role="status">
          {toast}
          <button aria-label="Dismiss" onClick={() => setToast("")}>
            ×
          </button>
        </div>
      )}
    </Context.Provider>
  );
}
