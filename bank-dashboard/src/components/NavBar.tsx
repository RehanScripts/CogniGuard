import { NavLink, useNavigate } from "react-router-dom";

import { clearAdminToken } from "../api";

const LINKS = [
  { to: "/", label: "Live" },
  { to: "/cases", label: "Cases" },
  { to: "/policy", label: "Policy" },
  { to: "/governance", label: "Governance" },
];

export default function NavBar() {
  const navigate = useNavigate();

  function handleLogout() {
    clearAdminToken();
    navigate("/login");
  }

  return (
    <nav className="flex items-center gap-4 bg-cbi-primary px-4 py-3 text-white shadow-sm">
      <span className="flex items-center gap-2 font-semibold">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-white text-xs font-bold text-cbi-primary">
          CB
        </span>
        CogniGuard SOC
      </span>
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) => (isActive ? "underline" : "text-cbi-primary-light")}
        >
          {link.label}
        </NavLink>
      ))}
      <button onClick={handleLogout} className="ml-auto text-sm text-cbi-primary-light hover:text-white">
        Log out
      </button>
    </nav>
  );
}
