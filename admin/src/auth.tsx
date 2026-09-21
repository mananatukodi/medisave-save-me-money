import { useContext, createContext, useEffect, useState, type ReactNode } from "react";
import { fetchMe, login as apiLogin, setToken, type Me } from "./api";

interface AuthState {
  me: Me | null;
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  signIn: async () => {},
  signOut: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session on first mount.
  useEffect(() => {
    void (async () => {
      const restored = await fetchMe();
      setMe(restored);
      setLoading(false);
    })();
  }, []);

  const signIn = async (email: string, password: string) => {
    const user = await apiLogin(email, password);
    setMe(user);
  };

  const signOut = () => {
    setToken(null);
    setMe(null);
  };

  return (
    <AuthContext.Provider value={{ me, loading, signIn, signOut }}>{children}</AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
