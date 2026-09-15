// Auth context: session state from localStorage + /auth/me refresh.

"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  api,
  clearSession,
  getCachedUser,
  getToken,
  setSession,
  ApiError,
  NetworkError,
} from "@/lib/api";
import type { LoginResponse, User } from "@/lib/types";

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: {
    email: string;
    password: string;
    full_name: string;
    phone?: string;
    language?: string;
  }) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const router = useRouter();

  useEffect(() => {
    let cancelled = false;
    const token = getToken();
    if (!token) {
      setReady(true);
      return;
    }
    setUser(getCachedUser());
    api
      .me()
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.status === 401 && !cancelled) {
          clearSession();
          setUser(null);
        }
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res: LoginResponse = await api.login(email, password);
      setSession(res.access_token, res.user);
      setUser(res.user);
      return res.user;
    },
    [],
  );

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      full_name: string;
      phone?: string;
      language?: string;
    }) => {
      const res = await api.register(input);
      setSession(res.access_token, res.user);
      setUser(res.user);
      return res.user;
    },
    [],
  );

  const logout = useCallback(() => {
    clearSession();
    setUser(null);
    router.push("/login");
  }, [router]);

  const value = useMemo(
    () => ({ user, ready, login, register, logout }),
    [user, ready, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export { NetworkError };
