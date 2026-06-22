import React from "react";
import ReactDOM from "react-dom/client";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import "./index.css";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import Security from "./pages/Security";
import StepUp from "./pages/StepUp";
import Transactions from "./pages/Transactions";
import Transfer from "./pages/Transfer";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/step-up" element={<StepUp />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/transfer" element={<Transfer />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/security" element={<Security />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
