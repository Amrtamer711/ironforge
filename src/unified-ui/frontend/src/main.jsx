import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { ThemeProvider } from "next-themes";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import "./styles/globals.css";
import { AppRoutes } from "./routes/AppRoutes";
import { AuthProvider } from "./state/auth";
import { NotificationsProvider } from "./state/notifications";

const BRAND_KEY = "mmg-brand-theme";

if (typeof window !== "undefined") {
  const storedBrand = window.localStorage.getItem(BRAND_KEY);
  if (storedBrand && storedBrand !== "none") {
    document.body.setAttribute("data-brand-theme", storedBrand);
  } else {
    document.body.removeAttribute("data-brand-theme");
  }
}

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <NotificationsProvider>
            <BrowserRouter>
              <AppRoutes />
            </BrowserRouter>
          </NotificationsProvider>
        </AuthProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </React.StrictMode>
);
