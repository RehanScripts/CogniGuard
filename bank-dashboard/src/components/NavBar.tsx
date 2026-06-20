import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/", label: "Live" },
  { to: "/cases", label: "Cases" },
  { to: "/policy", label: "Policy" },
  { to: "/governance", label: "Governance" },
];

export default function NavBar() {
  return (
    <nav className="flex items-center gap-4 border-b bg-gray-900 px-4 py-3 text-white">
      <span className="font-semibold">CogniGuard SOC</span>
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) => (isActive ? "underline" : "text-gray-300")}
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  );
}
