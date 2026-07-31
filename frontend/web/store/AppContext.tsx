"use client";

/** App-level context: API base URL + theme, persisted in localStorage. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { DEFAULT_API_BASE, setApiBase } from "@/lib/api";

const THEME_KEY = "acce.theme";
const API_BASE_KEY = "acce.apiBase";

type Theme = "dark" | "light";

interface AppState {
  theme: Theme;
  toggleTheme: () => void;
  apiBase: string;
  updateApiBase: (base: string) => void;
}

const AppContext = createContext<AppState | null>(null);

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("light", theme === "light");
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>("dark");
  const [apiBase, setState] = useState<string>(DEFAULT_API_BASE);

  useEffect(() => {
    applyTheme(theme);
    localStorage.setItem(THEME_KEY, theme);
  }, [theme]);

  useEffect(() => {
    const savedTheme = localStorage.getItem(THEME_KEY);
    if (savedTheme === "light" || savedTheme === "dark") setTheme(savedTheme);
    const savedBase = localStorage.getItem(API_BASE_KEY);
    if (savedBase) {
      setApiBase(savedBase);
      setState(savedBase);
    }
  }, []);

  const toggleTheme = useCallback(() => setTheme((t) => (t === "dark" ? "light" : "dark")), []);

  const updateApiBase = useCallback((base: string) => {
    setApiBase(base);
    setState(base);
    localStorage.setItem(API_BASE_KEY, base);
  }, []);

  const value = useMemo(
    () => ({ theme, toggleTheme, apiBase, updateApiBase }),
    [theme, toggleTheme, apiBase, updateApiBase],
  );

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used inside <AppProvider>");
  return ctx;
}
