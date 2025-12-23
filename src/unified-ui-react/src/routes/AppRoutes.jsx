import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { LandingPage } from "../screens/LandingPage";
import { LoginPage } from "../screens/LoginPage";
import { AuthCallback } from "../screens/AuthCallback";
import { AppShell } from "../shell/AppShell";
import { ChatPage } from "../screens/tools/ChatPage";
import { MockupPage } from "../screens/tools/MockupPage";
import { ProposalsPage } from "../screens/tools/ProposalsPage";
import { AdminPage } from "../screens/tools/AdminPage";
import { ProtectedRoute } from "./ProtectedRoute";
import { SettingsPage } from "../screens/tools/SettingsPage";
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<Navigate to="chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="mockup" element={<MockupPage />} />
        <Route path="proposals" element={<ProposalsPage />} />
        <Route path="admin" element={<AdminPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
