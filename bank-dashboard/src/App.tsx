import type { ReactElement } from "react";
import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import { getAdminToken } from "./api";
import NavBar from "./components/NavBar";
import AdminLogin from "./pages/AdminLogin";
import Cases from "./pages/Cases";
import Governance from "./pages/Governance";
import Live from "./pages/Live";
import Policy from "./pages/Policy";
import UserDetail from "./pages/UserDetail";

function RequireAuth({ children }: { children: ReactElement }) {
  if (!getAdminToken()) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<AdminLogin />} />
        <Route
          path="*"
          element={
            <RequireAuth>
              <>
                <NavBar />
                <main className="p-4">
                  <Routes>
                    <Route path="/" element={<Live />} />
                    <Route path="/users/:userId" element={<UserDetail />} />
                    <Route path="/policy" element={<Policy />} />
                    <Route path="/cases" element={<Cases />} />
                    <Route path="/governance" element={<Governance />} />
                    <Route path="*" element={<Navigate to="/" replace />} />
                  </Routes>
                </main>
              </>
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
