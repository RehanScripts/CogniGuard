import { Navigate, Route, BrowserRouter, Routes } from "react-router-dom";

import NavBar from "./components/NavBar";
import Cases from "./pages/Cases";
import Governance from "./pages/Governance";
import Live from "./pages/Live";
import Policy from "./pages/Policy";
import UserDetail from "./pages/UserDetail";

export default function App() {
  return (
    <BrowserRouter>
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
    </BrowserRouter>
  );
}
