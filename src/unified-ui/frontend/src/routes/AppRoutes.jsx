import React from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { LoginPage } from "../screens/LoginPage";
import { AuthCallback } from "../screens/AuthCallback";
import { AppShell } from "../shell/AppShell";
import { ChatPage } from "../screens/ChatPage";
import { MockupPage } from "../screens/MockupPage";
import { ProposalsPage } from "../screens/ProposalsPage";
import { AdminPage } from "../screens/AdminPage";
import { NotificationsPage } from "../screens/NotificationsPage";
import { VideoCritiqueAssistantPage } from "../screens/VideoCritiqueAssistantPage";
import { AssetManagementPage } from "../screens/AssetManagementPage";
// import { CostDashboardPage } from "../screens/CostDashboardPage";
import { ProtectedRoute } from "./ProtectedRoute";
import { SettingsPage } from "../screens/SettingsPage";
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/app" element={<ProtectedRoute><AppShell /></ProtectedRoute>}>
        <Route index element={<Navigate to="chat" replace />} />
        <Route path="chat" element={<ChatPage />} />
        <Route path="video-critique" element={<VideoCritiqueAssistantPage />} />
        <Route path="mockup" element={<MockupPage />} />
        <Route path="proposals" element={<ProposalsPage />} />
        <Route path="notifications" element={<NotificationsPage />} />
        {/*
        <Route path="costs" element={<CostDashboardPage />} />
        */}
        <Route path="admin" element={<AdminPage />} />
        <Route path="asset-management" element={<AssetManagementPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
