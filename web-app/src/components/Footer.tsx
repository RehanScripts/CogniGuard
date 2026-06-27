import { Smartphone } from "lucide-react";

// Static brand footer shared by every authenticated page (Dashboard/Transfer/Transactions/Security).
export default function Footer() {
  return (
    <footer className="mt-auto border-t border-outline-variant bg-surface-container-lowest py-6">
      <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-4 px-4 text-xs md:flex-row md:px-8">
        <div className="flex flex-col items-center md:items-start">
          <span className="font-bold text-primary">Central Bank of India</span>
          <p className="mt-1 text-on-surface-variant">&copy; 2026 Central Bank of India. All rights reserved.</p>
        </div>

        <div className="flex flex-wrap justify-center gap-6">
          <a className="text-on-surface-variant transition-all hover:text-primary hover:underline" href="#">
            Privacy Policy
          </a>
          <a className="text-on-surface-variant transition-all hover:text-primary hover:underline" href="#">
            Terms of Service
          </a>
          <a className="text-on-surface-variant transition-all hover:text-primary hover:underline" href="#">
            Security Tips
          </a>
          <a className="text-on-surface-variant transition-all hover:text-primary hover:underline" href="#">
            Contact Us
          </a>
        </div>

        <div className="flex items-center gap-2 font-bold text-primary">
          <Smartphone className="h-4 w-4" />
          <span>1800-CBI-SECURE</span>
        </div>
      </div>
    </footer>
  );
}
