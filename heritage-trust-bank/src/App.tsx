/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState, useEffect, useRef } from "react";
import {
  Shield,
  Lock,
  User,
  Eye,
  EyeOff,
  Keyboard,
  ArrowRight,
  HelpCircle,
  Bell,
  CheckCircle,
  AlertOctagon,
  LogOut,
  Info,
  CreditCard,
  TrendingDown,
  TrendingUp,
  Search,
  Filter,
  Download,
  DollarSign,
  Briefcase,
  ChevronRight,
  Smartphone,
  Send,
  Home,
  Check,
  RefreshCw,
  Clock,
  ShieldAlert
} from "lucide-react";
import {
  CogniGuardBehavior,
  LoginResponse,
  StepUpChallenge,
  ProfileOut,
  AccountOut,
  TransactionOut
} from "./types";
import CogniGuardSimulator from "./components/CogniGuardSimulator";

export default function App() {
  // Session & Authentication states
  const [sessionToken, setSessionToken] = useState<string | null>(
    localStorage.getItem("htb_session_token")
  );
  const [currentView, setCurrentView] = useState<"login" | "step-up" | "dashboard">(
    localStorage.getItem("htb_session_token") ? "dashboard" : "login"
  );

  // Login form states
  const [customerId, setCustomerId] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [rememberId, setRememberId] = useState(false);
  const [loginError, setLoginError] = useState<{ action?: string; retryAfter?: number } | null>(null);
  const [loginLoading, setLoginLoading] = useState(false);

  // Interactive virtual keypad simulation state
  const [showVirtualKeypadMsg, setShowVirtualKeypadMsg] = useState(false);

  // Active CogniGuard behavioral state (Steady human preset initially)
  const [behavior, setBehavior] = useState<CogniGuardBehavior>({
    profileName: "Standard Owner Profile",
    keystrokeCadence: "steady",
    deviceFingerprint: "Chrome-MacOS-StableFingerprint-9938b",
    locationMatched: true,
    mousePathAnomalies: false,
  });

  // Security headers returned from login
  const [lastEnrollment, setLastEnrollment] = useState<string | null>(null);
  const [lastTrustScore, setLastTrustScore] = useState<number | null>(null);
  const [lastBehaviorMatchScore, setLastBehaviorMatchScore] = useState<number | null>(null);

  // Step-up verification states
  const [activeChallenge, setActiveChallenge] = useState<StepUpChallenge | null>(null);
  const [otpFields, setOtpFields] = useState<string[]>(["", "", "", "", "", ""]);
  const [stepUpError, setStepUpError] = useState<string | null>(null);
  const [stepUpLoading, setStepUpLoading] = useState(false);
  const [timerCount, setTimerCount] = useState(179); // 2:59 in seconds
  const otpRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Banking profile states
  const [profile, setProfile] = useState<ProfileOut | null>(null);
  const [accounts, setAccounts] = useState<AccountOut[]>([]);
  const [transactions, setTransactions] = useState<TransactionOut[]>([]);
  const [dashboardLoading, setDashboardLoading] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [transactionLimit, setTransactionLimit] = useState(5);

  // Load Remembered ID on mount
  useEffect(() => {
    const savedId = localStorage.getItem("htb_remembered_id");
    if (savedId) {
      setCustomerId(savedId);
      setRememberId(true);
    }
  }, []);

  // Countdown timer for step-up verification screen
  useEffect(() => {
    if (currentView !== "step-up") return;
    const timer = setInterval(() => {
      setTimerCount((prev) => {
        if (prev <= 1) {
          clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [currentView]);

  // Countdown timer for lockout duration
  useEffect(() => {
    if (!loginError || !loginError.retryAfter || loginError.retryAfter <= 0) return;
    const interval = setInterval(() => {
      setLoginError((prev) => {
        if (!prev || !prev.retryAfter || prev.retryAfter <= 1) {
          clearInterval(interval);
          return null;
        }
        return { ...prev, retryAfter: prev.retryAfter - 1 };
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [loginError]);

  // Retrieve Banking info once session is active
  useEffect(() => {
    if (sessionToken && currentView === "dashboard") {
      fetchBankingData();
    }
  }, [sessionToken, currentView, transactionLimit]);

  const fetchBankingData = async () => {
    setDashboardLoading(true);
    try {
      // API call for profile info
      const profileRes = await fetch("/api/v1/banking/profile", {
        headers: { Authorization: `Bearer ${sessionToken}` }
      });
      if (profileRes.ok) {
        const pData = await profileRes.json();
        setProfile(pData);
      } else if (profileRes.status === 401) {
        handleLogout();
        return;
      }

      // API call for account list
      const accountsRes = await fetch("/api/v1/banking/accounts", {
        headers: { Authorization: `Bearer ${sessionToken}` }
      });
      if (accountsRes.ok) {
        const aData = await accountsRes.json();
        setAccounts(aData);
      }

      // API call for transactions list
      const txRes = await fetch(`/api/v1/banking/transactions?limit=${transactionLimit}`, {
        headers: { Authorization: `Bearer ${sessionToken}` }
      });
      if (txRes.ok) {
        const tData = await txRes.json();
        setTransactions(tData);
      }
    } catch (err) {
      console.error("Error retrieving banking data:", err);
    } finally {
      setDashboardLoading(false);
    }
  };

  // Login handler
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!customerId || !password) {
      setLoginError({ action: "Please complete both Customer ID and Password fields.", retryAfter: 3 });
      return;
    }

    setLoginLoading(true);
    setLoginError(null);

    try {
      const res = await fetch("/api/v1/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: customerId,
          password: password,
          behavior: behavior
        })
      });

      const data = (await res.json()) as LoginResponse;

      if (!res.ok) {
        setLoginError({
          action: data.hardening?.action || "Authentication failed. Incorrect password credentials.",
          retryAfter: data.retry_after_s || 5
        });
        return;
      }

      // Handle custom scores returned to drive the UI headers
      if (data.enrollment) setLastEnrollment(data.enrollment);
      if (data.trust_score) setLastTrustScore(data.trust_score);
      if (data.behavior_match_score) setLastBehaviorMatchScore(data.behavior_match_score);

      if (data.action === "allow" && data.session_token) {
        // Successful steady human pattern
        localStorage.setItem("htb_session_token", data.session_token);
        if (rememberId) {
          localStorage.setItem("htb_remembered_id", customerId);
        } else {
          localStorage.removeItem("htb_remembered_id");
        }
        setSessionToken(data.session_token);
        setCurrentView("dashboard");
      } else if (data.action === "verify" && data.challenge) {
        // Step-up required
        setActiveChallenge(data.challenge);
        setOtpFields(["", "", "", "", "", ""]);
        setTimerCount(179);
        setCurrentView("step-up");
      } else if (data.action === "block") {
        // Locked out
        setLoginError({
          action: data.hardening?.action || "Your account has been locked due to high-risk behavioral anomalies.",
          retryAfter: data.retry_after_s || 3600
        });
      }
    } catch (err) {
      setLoginError({ action: "Failed to connect to secure bank server. Please try again later.", retryAfter: 5 });
    } finally {
      setLoginLoading(false);
    }
  };

  // OTP field entry navigation
  const handleOtpChange = (val: string, index: number) => {
    const updatedOtp = [...otpFields];
    updatedOtp[index] = val.substring(val.length - 1); // allow only 1 char
    setOtpFields(updatedOtp);
    setStepUpError(null);

    if (val && index < 5) {
      otpRefs.current[index + 1]?.focus();
    }
  };

  const handleOtpKeyDown = (e: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    if (e.key === "Backspace" && !otpFields[index] && index > 0) {
      otpRefs.current[index - 1]?.focus();
    }
  };

  // Step-up Submit Code Verification
  const handleStepUpVerify = async (codeOverride?: string) => {
    const finalCode = codeOverride || otpFields.join("");
    if (!finalCode || (finalCode.length < 6 && !codeOverride)) {
      setStepUpError("Please enter the complete 6-digit verification code.");
      return;
    }

    setStepUpLoading(true);
    setStepUpError(null);

    try {
      const challengeId = activeChallenge?.challenge_id || "challenge_otp_9982";
      const res = await fetch("/api/v1/auth/step-up/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          challenge_id: challengeId,
          otp_or_assertion: finalCode
        })
      });

      const data = await res.json();

      if (res.status === 404) {
        // stale challenge -> back to login
        setLoginError({ action: data.error || "Challenge has expired or is invalid.", retryAfter: 5 });
        setCurrentView("login");
        return;
      }

      if (!res.ok) {
        setStepUpError(data.error || "Incorrect code, try again.");
        return;
      }

      if (data.action === "allow" && data.session_token) {
        localStorage.setItem("htb_session_token", data.session_token);
        if (rememberId) {
          localStorage.setItem("htb_remembered_id", customerId);
        }
        setSessionToken(data.session_token);
        setCurrentView("dashboard");
      }
    } catch (err) {
      setStepUpError("Failed to communicate verification assertion.");
    } finally {
      setStepUpLoading(false);
    }
  };

  // Biometric verification assertion button
  const simulateBiometricAssertion = () => {
    setStepUpLoading(true);
    setTimeout(() => {
      handleStepUpVerify("biometric_assertion_success");
    }, 1200);
  };

  const handleLogout = () => {
    localStorage.removeItem("htb_session_token");
    setSessionToken(null);
    setCurrentView("login");
    setPassword("");
    setLastEnrollment(null);
    setLastTrustScore(null);
    setLastBehaviorMatchScore(null);
  };

  // Formatting utility for OTP timer display
  const formatTime = (secs: number) => {
    const mins = Math.floor(secs / 60);
    const remainingSecs = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${remainingSecs.toString().padStart(2, "0")}`;
  };

  // Filter transaction items based on user search query
  const filteredTransactions = transactions.filter((tx) =>
    tx.description.toLowerCase().includes(searchQuery.toLowerCase()) ||
    tx.type.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="min-h-screen flex flex-col font-sans selection:bg-primary selection:text-white">
      
      {/* ----------------- LOGIN VIEW ----------------- */}
      {currentView === "login" && (
        <div className="flex-grow flex flex-col relative overflow-hidden bg-background-custom">
          {/* Majestical Stone columns bank background overlay */}
          <div className="absolute inset-0 z-0 bg-cover bg-center opacity-10" style={{ backgroundImage: "radial-gradient(circle at 2px 2px, #c1c7d3 1px, transparent 0)", strokeDashoffset: "24" }} />
          <div 
            className="absolute inset-0 z-0 bg-cover bg-center grayscale opacity-15 blur-[1px] scale-105 pointer-events-none" 
            style={{ backgroundImage: `url('https://lh3.googleusercontent.com/aida-public/AB6AXuDLVjXPcHk5D-i3gXChyGU5-j9e9m8KjvPIUNzg1HruewK6XRPCVW_hCytK2bAz-yV7CpQNdREX5R2yismhKX-e1JmC-ujJT2Ri4kFkK8o6hWM9bq-pU3BeLEoXTyj6J5kxvb4To5hiLjSAZ-pHjnxlmCq0nIeu498ifgs39mL-1ny-dOwSxv5g9SHq07ITc4QhSsrcPjyB5KpwHzSosf9Ke13l3SadbEp-z0KRSZO5glZ0qqulkaBttKxaPuxDLjASCExgVZ1N270')` }}
          />

          {/* Secure Header Info with Trust Score Calibration Badge */}
          {(lastEnrollment || lastTrustScore !== null) && (
            <div className="w-full bg-slate-900 border-b border-slate-700 py-3 px-6 text-slate-300 z-10 flex flex-wrap justify-between items-center gap-4 animate-fade-in shadow-inner">
              <div className="flex items-center gap-2">
                <ShieldAlert className="w-5 h-5 text-emerald-400" />
                <span className="text-xs font-semibold font-headline">CogniGuard Heuristics Framework:</span>
                <span className="text-xs bg-slate-800 text-emerald-300 px-2 py-0.5 rounded font-mono border border-emerald-950">
                  {lastEnrollment || "Calibration: Enrolled"}
                </span>
              </div>
              
              <div className="flex gap-4">
                {lastTrustScore !== null && (
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-slate-400">Trust Score:</span>
                    <span className={`px-2 py-0.5 rounded font-mono font-bold ${lastTrustScore > 80 ? "text-emerald-400 bg-emerald-950/40 border border-emerald-900" : lastTrustScore > 40 ? "text-amber-400 bg-amber-950/40 border border-amber-900" : "text-rose-400 bg-rose-950/40 border border-rose-900"}`}>
                      {lastTrustScore}/100
                    </span>
                  </div>
                )}
                {lastBehaviorMatchScore !== null && (
                  <div className="flex items-center gap-1.5 text-xs">
                    <span className="text-slate-400">Behavioral Match:</span>
                    <span className={`px-2 py-0.5 rounded font-mono font-bold ${lastBehaviorMatchScore > 80 ? "text-emerald-400 bg-emerald-950/40 border border-emerald-900" : "text-rose-400 bg-rose-950/40 border border-rose-900"}`}>
                      {lastBehaviorMatchScore}%
                    </span>
                  </div>
                )}
              </div>
            </div>
          )}

          <div className="flex-grow flex items-center justify-center py-10 px-4 md:px-8 z-10">
            <div className="max-w-6xl w-full flex flex-col lg:flex-row gap-8 items-center justify-center">
              
              {/* Left Side: Secure Login card container */}
              <div className="w-full max-w-[440px] bg-surface-container-lowest border border-outline-variant rounded-xl shadow-xl p-8 md:p-10 transition-transform duration-300 hover:scale-[1.01]">
                
                {/* Brand Header */}
                <div className="flex flex-col items-center mb-8">
                  <img 
                    alt="Heritage Trust Bank" 
                    className="h-16 w-auto mb-4 object-contain transition-transform duration-300 hover:rotate-3" 
                    src="https://lh3.googleusercontent.com/aida-public/AB6AXuAU_FcoRU5GfTy6BULNzDUDucl5kJ9gS6k0_ARnF5xP_nGxRUb0gRvk5rs1mwjNrPYI94_4OPDJXh8YI4fBGBO-c56amlT7mswOCKkZHOhm2NtDH1DsVYS-wDE3wfP_KgMfxOFuleRf31UzmfbRSFtpFKhzW6IMmFW1oTeEkAFGogu3nJOJuhOQXmXlKwd6fADMCiNZ85COJgYXDBaM41Z5WHB3EqZbYj2SKVLzl7rvnCm-AffobpjRSOrYlxMao18VqbN0eqZEfV4"
                  />
                  <h1 className="font-headline text-2xl font-bold text-primary tracking-tight">Heritage Trust Bank</h1>
                  <p className="text-xs text-on-surface-variant font-medium mt-1 uppercase tracking-widest text-center">Secure Portal Access</p>
                </div>

                {/* Hardened Error Lockout Banner */}
                {loginError && (
                  <div className="mb-6 p-4 bg-rose-50 border border-rose-200 text-rose-800 rounded-lg flex gap-3 animate-fade-in text-xs leading-relaxed">
                    <AlertOctagon className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-semibold text-rose-900">Cognitive Blocker Enabled</p>
                      <p className="mt-1">{loginError.action}</p>
                      {loginError.retryAfter && loginError.retryAfter > 0 ? (
                        <p className="mt-2 text-rose-700 font-mono font-bold flex items-center gap-1.5 bg-rose-100/60 px-2 py-0.5 rounded w-max">
                          <Clock className="w-3.5 h-3.5" />
                          Retry lockout counter: {loginError.retryAfter}s
                        </p>
                      ) : null}
                    </div>
                  </div>
                )}

                {/* Login Form */}
                <form className="space-y-5" onSubmit={handleLoginSubmit}>
                  
                  {/* Customer ID Field */}
                  <div className="space-y-1.5">
                    <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="customer_id">
                      Customer ID
                    </label>
                    <div className="relative group rounded-lg">
                      <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                        <User className="w-4 h-4" />
                      </span>
                      <input 
                        id="customer_id"
                        name="customer_id"
                        type="text"
                        disabled={loginLoading || (!!loginError && loginError.retryAfter !== undefined && loginError.retryAfter > 0)}
                        placeholder="Enter your banking ID (e.g. 9827341)"
                        value={customerId}
                        onChange={(e) => setCustomerId(e.target.value)}
                        className="w-full pl-10 pr-4 py-3 bg-white border border-outline-variant rounded-lg focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-slate-300 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                      />
                    </div>
                  </div>

                  {/* Password Field */}
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-center">
                      <label className="block text-xs font-semibold text-on-surface-variant" htmlFor="password">
                        Password
                      </label>
                      <button 
                        type="button" 
                        onClick={() => alert("Credentials are configured internally for demonstration. Password: 'password123'. Change profile settings on the inspector panel to see adaptive results.")}
                        className="text-xs text-primary hover:underline transition-all font-medium"
                      >
                        Forgot Password?
                      </button>
                    </div>
                    <div className="relative group rounded-lg">
                      <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline group-focus-within:text-primary transition-colors">
                        <Lock className="w-4 h-4" />
                      </span>
                      <input 
                        id="password"
                        name="password"
                        type={showPassword ? "text" : "password"}
                        disabled={loginLoading || (!!loginError && loginError.retryAfter !== undefined && loginError.retryAfter > 0)}
                        placeholder="••••••••"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        className="w-full pl-10 pr-10 py-3 bg-white border border-outline-variant rounded-lg focus:border-primary focus:ring-1 focus:ring-primary outline-none transition-all placeholder:text-slate-300 text-sm disabled:bg-slate-50 disabled:text-slate-400"
                      />
                      <button 
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-outline hover:text-on-surface transition-colors"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>

                  {/* Security Options */}
                  <div className="flex items-center justify-between py-1 text-xs">
                    <div className="flex items-center space-x-2">
                      <input 
                        id="remember"
                        type="checkbox"
                        checked={rememberId}
                        onChange={(e) => setRememberId(e.target.checked)}
                        className="w-4 h-4 text-primary border-outline-variant rounded focus:ring-primary"
                      />
                      <label className="text-on-surface-variant cursor-pointer" htmlFor="remember">
                        Remember ID
                      </label>
                    </div>
                    <button 
                      type="button"
                      onClick={() => {
                        setShowVirtualKeypadMsg(true);
                        setTimeout(() => setShowVirtualKeypadMsg(false), 3000);
                      }}
                      className="flex items-center gap-1.5 text-primary-container bg-primary-fixed/20 px-2.5 py-1 rounded hover:bg-primary-fixed/30 transition-all font-medium"
                    >
                      <Keyboard className="w-3.5 h-3.5" />
                      <span>Virtual Keypad</span>
                    </button>
                  </div>

                  {/* Keyboard Activation Notification */}
                  {showVirtualKeypadMsg && (
                    <div className="p-2 bg-slate-900 text-white rounded text-[10px] animate-fade-in flex items-center gap-1.5">
                      <Info className="w-3 h-3 text-emerald-400" />
                      <span>Security Virtual Keypad activated in secure RAM segment.</span>
                    </div>
                  )}

                  {/* Login Button */}
                  <button 
                    type="submit"
                    disabled={loginLoading || (!!loginError && loginError.retryAfter !== undefined && loginError.retryAfter > 0)}
                    className="w-full bg-primary hover:bg-primary-container text-on-primary font-bold py-3.5 rounded-lg shadow-md active:scale-[0.99] transition-all flex items-center justify-center gap-2 text-sm disabled:bg-slate-300 disabled:cursor-not-allowed"
                  >
                    {loginLoading ? (
                      <span className="flex items-center gap-2">
                        <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                        Analyzing Keystrokes...
                      </span>
                    ) : (
                      <>
                        <span>Secure Login</span>
                        <ArrowRight className="w-4 h-4" />
                      </>
                    )}
                  </button>

                  {/* New User Action */}
                  <div className="pt-4 border-t border-outline-variant text-center text-xs">
                    <p className="text-on-surface-variant mb-1.5">Don't have an online account?</p>
                    <button 
                      type="button"
                      onClick={() => alert("Please contact Heritage Bank Relationship Manager to request enrollment credentials.")}
                      className="inline-flex items-center gap-1 font-semibold text-primary hover:text-primary-container transition-colors group"
                    >
                      <span>New User Registration</span>
                      <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
                    </button>
                  </div>
                </form>

                {/* Security Badges */}
                <div className="mt-6 flex justify-center items-center gap-4 border-t border-slate-100 pt-4 opacity-70 text-[10px] font-bold text-slate-500 uppercase tracking-wider">
                  <div className="flex items-center gap-1">
                    <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
                    <span>SSL Secured</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Shield className="w-3.5 h-3.5 text-primary" />
                    <span>256-Bit Encrypted</span>
                  </div>
                </div>

              </div>

              {/* Right Side: CogniGuard Simulator panel */}
              <div className="w-full max-w-sm flex flex-col gap-4 animate-fade-in">
                <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm text-xs leading-relaxed text-slate-600">
                  <h3 className="font-headline font-bold text-sm text-slate-900 mb-2">Simulation Sandbox Instructions</h3>
                  <p className="mb-2">
                    Heritage Bank utilizes adaptive profiling via the <strong>CogniGuard Behavioral Engine</strong>. Toggle the settings in the inspector panel below, then trigger the login form:
                  </p>
                  <ul className="list-disc pl-4 space-y-1">
                    <li><strong>Steady Human:</strong> Perfect human keystroke dynamics. Returns direct dashboard entry.</li>
                    <li><strong>Anomalous:</strong> Triggers step-up verification. Demands MFA challenge code.</li>
                    <li><strong>Robotic:</strong> Imitates automated browser bot tools. Triggers absolute security lockout.</li>
                  </ul>
                  <p className="mt-2.5 font-semibold text-slate-800">Demo Customer ID: <span className="font-mono bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">9827341</span></p>
                  <p className="font-semibold text-slate-800">Demo Password: <span className="font-mono bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded">password123</span></p>
                </div>

                <CogniGuardSimulator activeBehavior={behavior} onBehaviorChange={(b) => setBehavior(b)} />
              </div>

            </div>
          </div>

          {/* Minimal Language Footer Support */}
          <div className="mt-auto py-4 bg-slate-100 border-t border-slate-200 text-center text-xs text-on-surface-variant flex flex-wrap justify-center gap-4 z-10">
            <button className="hover:text-primary font-medium" onClick={() => {}}>English</button>
            <span className="text-outline-variant">|</span>
            <button className="hover:text-primary font-medium" onClick={() => {}}>हिंदी</button>
            <span className="text-outline-variant">|</span>
            <button className="hover:text-primary font-medium" onClick={() => {}}>मराठी</button>
          </div>
        </div>
      )}


      {/* ----------------- STEP-UP MFA VIEW ----------------- */}
      {currentView === "step-up" && (
        <div className="flex-grow flex flex-col justify-center items-center relative py-12 px-4 bg-background-custom">
          {/* Suppressed background layout elements */}
          <div className="absolute inset-0 z-0 opacity-15" style={{ backgroundImage: "radial-gradient(circle at 1px 1px, #717783 1px, transparent 0)", backgroundSize: "32px 32px" }} />
          
          <main className="w-full max-w-[480px] z-10 animate-fade-in">
            <div className="bg-surface-container-lowest rounded-xl border border-outline-variant border-t-4 border-t-primary shadow-lg p-8 flex flex-col items-center">
              
              {/* Shield lock MFA icon */}
              <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mb-6 border border-slate-200">
                <Shield className="w-8 h-8 text-primary fill-slate-200" />
              </div>

              {/* Step-up titles */}
              <h1 className="font-headline text-2xl font-bold text-on-surface text-center mb-2">Verify it's you</h1>
              <p className="text-xs text-on-surface-variant text-center mb-8 px-4 leading-relaxed">
                We've sent a 6-digit verification code to your registered mobile number ending in •••• 8291.
              </p>

              {/* Stale/MFA Error Display */}
              {stepUpError && (
                <div className="w-full mb-6 p-3 bg-rose-50 border border-rose-100 text-rose-800 rounded-lg text-xs font-semibold text-center animate-fade-in">
                  {stepUpError}
                </div>
              )}

              {/* 6-Digit OTP Box Grid */}
              <div className="flex gap-2.5 md:gap-3 mb-6" id="otp-container">
                {otpFields.map((field, idx) => (
                  <React.Fragment key={idx}>
                    <input 
                      ref={(el) => (otpRefs.current[idx] = el)}
                      type="text"
                      maxLength={1}
                      disabled={stepUpLoading}
                      value={field}
                      onChange={(e) => handleOtpChange(e.target.value, idx)}
                      onKeyDown={(e) => handleOtpKeyDown(e, idx)}
                      className="w-12 h-14 text-center text-xl font-bold border border-outline-variant rounded-lg bg-surface-bright focus:border-primary focus:ring-1 focus:ring-primary transition-all outline-none"
                    />
                    {idx === 2 && (
                      <div className="w-2 flex items-center justify-center text-outline-variant font-extrabold">-</div>
                    )}
                  </React.Fragment>
                ))}
              </div>

              {/* Sandbox info helpers */}
              <div className="mb-4 bg-slate-100 rounded border border-slate-200 py-1.5 px-3 text-[11px] text-slate-500 font-mono text-center w-full">
                Demo SMS OTP Code is: <span className="font-bold text-slate-800">123456</span>
              </div>

              {/* Countdown Timer */}
              <div className="flex flex-col items-center gap-2 mb-8">
                <div className="text-xs text-on-surface-variant font-medium flex items-center gap-1.5">
                  <Clock className="w-4 h-4 text-outline" />
                  <span>Resend in </span>
                  <span className="font-mono font-bold text-on-surface">{formatTime(timerCount)}</span>
                </div>
                <button 
                  type="button"
                  disabled={timerCount > 0}
                  onClick={() => {
                    setTimerCount(179);
                    setStepUpError(null);
                    alert("A new SMS verification code has been dispatched.");
                  }}
                  className={`text-xs font-semibold transition-opacity ${timerCount > 0 ? "text-slate-400 cursor-not-allowed opacity-50" : "text-primary hover:underline"}`}
                >
                  Resend code
                </button>
              </div>

              {/* Verify OTP Button */}
              <button 
                type="button"
                onClick={() => handleStepUpVerify()}
                disabled={stepUpLoading}
                className="w-full bg-primary hover:bg-primary-container text-on-primary font-headline font-bold py-4 rounded-lg shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all mb-4 disabled:bg-slate-300"
              >
                {stepUpLoading ? "Verifying Credentials..." : "Verify"}
              </button>

              {/* Biometric verification simulation */}
              <button 
                type="button"
                onClick={simulateBiometricAssertion}
                disabled={stepUpLoading}
                className="w-full bg-slate-550 hover:bg-slate-100 text-primary border border-primary/20 hover:border-primary/50 font-semibold py-3 rounded-lg text-xs transition-all active:scale-[0.99] mb-6 flex items-center justify-center gap-2"
              >
                <span>Simulate TouchID/FaceID Assertion</span>
              </button>

              {/* Threat Risk Notes */}
              <div className="flex gap-3 p-4 bg-slate-100 rounded-lg items-start text-left">
                <Info className="w-5 h-5 text-primary shrink-0 mt-0.5" />
                <p className="text-xs text-on-surface-variant leading-relaxed">
                  This additional step-up calibration check was triggered by our adaptive risk engine due to anomalous location parameters.
                </p>
              </div>

            </div>

            {/* Quick Redirect Back to Login */}
            <div className="mt-6 flex justify-between px-2 text-xs">
              <button 
                type="button"
                onClick={() => setCurrentView("login")}
                className="text-on-surface-variant hover:text-primary flex items-center gap-1"
              >
                <HelpCircle className="w-4 h-4" />
                <span>Return to Login Portal</span>
              </button>
              <div className="text-on-surface-variant flex items-center gap-1">
                <CheckCircle className="w-4 h-4 text-emerald-600" />
                <span>PCI-DSS Secured</span>
              </div>
            </div>
          </main>
        </div>
      )}


      {/* ----------------- BANKING DASHBOARD VIEW ----------------- */}
      {currentView === "dashboard" && (
        <div className="flex-grow flex flex-col bg-background-custom animate-fade-in">
          
          {/* Top Navigation Bar */}
          <header className="bg-primary text-on-primary shadow-md fixed top-0 w-full z-50 h-16">
            <div className="flex justify-between items-center w-full px-6 md:px-10 h-16 max-w-7xl mx-auto">
              
              <div className="flex items-center gap-3">
                <img 
                  alt="HTB" 
                  className="h-9 w-auto bg-white p-1 rounded" 
                  src="https://lh3.googleusercontent.com/aida-public/AB6AXuAU_FcoRU5GfTy6BULNzDUDucl5kJ9gS6k0_ARnF5xP_nGxRUb0gRvk5rs1mwjNrPYI94_4OPDJXh8YI4fBGBO-c56amlT7mswOCKkZHOhm2NtDH1DsVYS-wDE3wfP_KgMfxOFuleRf31UzmfbRSFtpFKhzW6IMmFW1oTeEkAFGogu3nJOJuhOQXmXlKwd6fADMCiNZ85COJgYXDBaM41Z5WHB3EqZbYj2SKVLzl7rvnCm-AffobpjRSOrYlxMao18VqbN0eqZEfV4"
                />
                <span className="font-headline text-lg md:text-xl font-bold tracking-tight">Heritage Trust Bank</span>
              </div>

              {/* Nav links */}
              <nav className="hidden lg:flex items-center gap-8">
                <button className="font-semibold border-b-2 border-on-primary pb-1 text-sm">Dashboard</button>
                <button className="text-on-primary/80 hover:text-on-primary text-sm font-medium transition-colors" onClick={() => alert("Selected sub-module details under active construction.")}>Accounts</button>
                <button className="text-on-primary/80 hover:text-on-primary text-sm font-medium transition-colors" onClick={() => alert("Selected sub-module details under active construction.")}>Transfers</button>
                <button className="text-on-primary/80 hover:text-on-primary text-sm font-medium transition-colors" onClick={() => alert("Selected sub-module details under active construction.")}>Investments</button>
                <button className="text-on-primary/80 hover:text-on-primary text-sm font-medium transition-colors" onClick={() => alert("Selected sub-module details under active construction.")}>Services</button>
              </nav>

              {/* Profile Avatar and Secure Logout */}
              <div className="flex items-center gap-4">
                <button className="p-2 hover:bg-primary-container rounded-full transition-colors relative" onClick={() => alert("No new notifications under active session.")}>
                  <Bell className="w-5 h-5 text-on-primary" />
                  <span className="absolute top-1 right-1 w-2.5 h-2.5 bg-secondary rounded-full"></span>
                </button>
                <button className="p-2 hover:bg-primary-container rounded-full transition-colors" onClick={() => alert("Online assistant available at: 1800-HTB-SECURE")}>
                  <HelpCircle className="w-5 h-5 text-on-primary" />
                </button>
                
                <div className="h-8 w-px bg-on-primary/20 mx-1 hidden sm:block"></div>

                {/* Secure Vikram profile visual */}
                <div className="flex items-center gap-2">
                  <div className="h-9 w-9 rounded-full bg-slate-300 overflow-hidden border-2 border-on-primary/20">
                    <img 
                      className="w-full h-full object-cover" 
                      alt="Vikram Sen" 
                      src="https://lh3.googleusercontent.com/aida-public/AB6AXuBEDVjv7BmvHDY1oiuoP5Yw4qKXOGB1G5PVRS-wPp-suewGBuC8sy39CHLJW0XL9mTrYqpM_LlMjznxDWPJjqA-sSvIxzzDQwvi4aHW7zYakwE_lOcWoSYaa1sxgXMj8WWQgZKnnrTDTnPOmJ35KbzsYhMqhsYHq54AMqNTWXAOwvuBFZZtZSbc31v0VBZ_AlN5AhBun5iML-W4JQOWu7OknGSO5k-gb-jFiTpJDjnVHTXdu_0x4DcgphBq-vquvg6iNtRU9Afdpq0"
                      referrerPolicy="no-referrer"
                    />
                  </div>
                  <span className="text-sm font-semibold hidden md:block">{profile?.full_name || "Vikram Sen"}</span>
                </div>

                <button 
                  onClick={handleLogout}
                  className="bg-secondary px-4 py-2 rounded font-semibold text-xs hover:opacity-90 active:scale-95 transition-all text-white flex items-center gap-1.5"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  <span>Secure Logout</span>
                </button>
              </div>

            </div>
          </header>

          <div className="flex pt-16 min-h-screen">
            
            {/* Side Navigation Bar */}
            <aside className="w-64 bg-surface-container-low border-r border-outline-variant h-[calc(100vh-64px)] fixed left-0 flex flex-col py-6 px-3 overflow-y-auto hidden md:flex">
              <div className="px-4 mb-6 pb-6 border-b border-outline-variant">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-surface-container-highest flex items-center justify-center text-primary font-bold">
                    VS
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-on-surface">{profile?.full_name || "Vikram Sen"}</h3>
                    <p className="text-[11px] text-on-surface-variant font-mono">ID: 9827341</p>
                  </div>
                </div>
                {profile?.kyc_level && (
                  <div className="mt-3 bg-emerald-50 text-emerald-800 border border-emerald-200 rounded px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-center">
                    {profile.kyc_level}
                  </div>
                )}
              </div>

              <nav className="flex-1 space-y-1">
                <button className="w-full flex items-center gap-3 px-4 py-3 bg-primary-container text-white rounded-lg font-bold text-sm text-left transition-all">
                  <Home className="w-4 h-4" />
                  <span>Overview</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container hover:text-on-surface rounded-lg transition-all text-sm text-left" onClick={() => alert("Sub-module transfer under active construction.")}>
                  <Send className="w-4 h-4" />
                  <span>Fund Transfer</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container hover:text-on-surface rounded-lg transition-all text-sm text-left" onClick={() => alert("Sub-module statements under active construction.")}>
                  <CreditCard className="w-4 h-4" />
                  <span>Cards</span>
                </button>
                <button className="w-full flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container hover:text-on-surface rounded-lg transition-all text-sm text-left" onClick={() => alert("Statements panel initialized.")}>
                  <Smartphone className="w-4 h-4" />
                  <span>Bill Payments</span>
                </button>
              </nav>

              <div className="mt-auto pt-6 border-t border-outline-variant space-y-1 text-xs">
                <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded-lg flex gap-2 mb-4">
                  <Shield className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-bold">SOC Split Policy:</span> No threat metrics exist on this contract for customer compliance safety.
                  </div>
                </div>

                <a className="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container hover:text-on-surface rounded-lg transition-all" href="#">
                  <span>Settings</span>
                </a>
                <a className="flex items-center gap-3 px-4 py-3 text-on-surface-variant hover:bg-surface-container hover:text-on-surface rounded-lg transition-all" href="#">
                  <span>Security Center</span>
                </a>
              </div>
            </aside>

            {/* Main Content Area */}
            <main className="ml-0 md:ml-64 flex-1 p-6 md:p-10 max-w-7xl mx-auto w-full">
              
              {/* Welcome Section Banner */}
              <div className="mb-8 flex flex-col md:flex-row md:items-end justify-between gap-4">
                <div>
                  <h1 className="font-headline text-3xl font-bold text-on-surface">Good Morning, {profile?.full_name?.split(" ")[0] || "Vikram"}</h1>
                  <p className="text-xs text-on-surface-variant font-medium mt-1">Last login: 24 May 2024, 09:15 AM IST (via Secure device: •••• 9938b)</p>
                </div>
                <button 
                  onClick={() => alert("Quick Transfer panel initialized. Limits: ₹2,00,000 daily.")}
                  className="flex items-center gap-2 bg-primary text-on-primary px-6 py-3 rounded-lg font-bold shadow-md hover:opacity-90 active:scale-95 transition-all text-sm shrink-0"
                >
                  <RefreshCw className="w-4 h-4" />
                  <span>Quick Transfer</span>
                </button>
              </div>

              {/* Accounts balance cards (bento design system style) */}
              {dashboardLoading && accounts.length === 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8 animate-pulse">
                  <div className="bg-white h-44 rounded-xl border border-outline-variant" />
                  <div className="bg-white h-44 rounded-xl border border-outline-variant" />
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                  {accounts.map((acc, index) => (
                    <div 
                      key={index}
                      className="bg-white p-6 rounded-xl border border-outline-variant border-t-4 border-t-primary shadow-sm hover:shadow-md transition-shadow relative overflow-hidden"
                    >
                      <div className="flex justify-between items-start mb-4">
                        <div>
                          <p className="text-[11px] font-bold text-on-surface-variant uppercase tracking-wider">{acc.type}</p>
                          <h2 className="font-headline text-xl font-bold text-on-surface">{acc.masked_account_number}</h2>
                        </div>
                        <CreditCard className={`w-6 h-6 ${index === 0 ? "text-primary" : "text-secondary"}`} />
                      </div>

                      <div className="mb-6">
                        <p className="text-xs text-on-surface-variant">{acc.detail}</p>
                        <p className={`font-headline text-3xl font-bold ${index === 0 ? "text-primary" : "text-secondary"}`}>
                          {acc.balance}
                        </p>
                        {acc.due_date && (
                          <p className="text-xs text-rose-600 font-semibold mt-1">Due Date: {acc.due_date}</p>
                        )}
                      </div>

                      <div className="flex gap-3">
                        <button 
                          onClick={() => alert(`Reviewing actions for ${acc.type}`)}
                          className={`flex-1 font-bold py-2 px-4 rounded text-xs transition-all ${index === 0 ? "bg-slate-100 text-primary hover:bg-primary hover:text-white" : "bg-secondary text-white hover:opacity-95"}`}
                        >
                          {index === 0 ? "View Details" : "Pay Now"}
                        </button>
                        <button 
                          onClick={() => alert("Downloading transactional statement payload.")}
                          className="px-3 border border-outline-variant rounded flex items-center justify-center hover:bg-slate-50 transition-colors"
                        >
                          <Download className="w-4 h-4 text-on-surface-variant" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                
                {/* Left side: Quick actions & Special offers */}
                <div className="lg:col-span-1 space-y-6">
                  
                  {/* Quick Action Grid */}
                  <div>
                    <h3 className="font-headline text-lg font-bold text-on-surface mb-4">Quick Actions</h3>
                    <div className="grid grid-cols-2 gap-3">
                      <button 
                        onClick={() => alert("Fund Transfer initiated.")}
                        className="flex flex-col items-center justify-center p-4 bg-white border border-outline-variant rounded-xl hover:border-primary hover:bg-primary/5 transition-all group text-center"
                      >
                        <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-all">
                          <Send className="w-4 h-4 text-primary group-hover:text-white" />
                        </div>
                        <span className="text-xs font-semibold text-on-surface">Transfer Funds</span>
                      </button>

                      <button 
                        onClick={() => alert("Bill pay panel initialized.")}
                        className="flex flex-col items-center justify-center p-4 bg-white border border-outline-variant rounded-xl hover:border-primary hover:bg-primary/5 transition-all group text-center"
                      >
                        <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-all">
                          <Smartphone className="w-4 h-4 text-primary group-hover:text-white" />
                        </div>
                        <span className="text-xs font-semibold text-on-surface">Pay Bills</span>
                      </button>

                      <button 
                        onClick={() => alert("Fixed deposits panel initialized.")}
                        className="flex flex-col items-center justify-center p-4 bg-white border border-outline-variant rounded-xl hover:border-primary hover:bg-primary/5 transition-all group text-center"
                      >
                        <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-all">
                          <Briefcase className="w-4 h-4 text-primary group-hover:text-white" />
                        </div>
                        <span className="text-xs font-semibold text-on-surface">Fixed Deposit</span>
                      </button>

                      <button 
                        onClick={() => alert("Contact security center initialized.")}
                        className="flex flex-col items-center justify-center p-4 bg-white border border-outline-variant rounded-xl hover:border-primary hover:bg-primary/5 transition-all group text-center"
                      >
                        <div className="w-10 h-10 bg-primary/10 rounded-full flex items-center justify-center mb-2 group-hover:bg-primary group-hover:text-white transition-all">
                          <Shield className="w-4 h-4 text-primary group-hover:text-white" />
                        </div>
                        <span className="text-xs font-semibold text-on-surface">Security Help</span>
                      </button>
                    </div>
                  </div>

                  {/* Special promotional home loan offer */}
                  <div className="bg-primary-container p-5 rounded-xl text-white relative overflow-hidden group">
                    <div className="relative z-10">
                      <h4 className="font-bold text-lg mb-1">Pre-approved Home Loan</h4>
                      <p className="text-xs opacity-90 mb-4 leading-relaxed">Up to ₹75 Lakhs with special ROI at 8.40%*</p>
                      <button 
                        onClick={() => alert("Home Loan pre-approval request recorded.")}
                        className="bg-white text-primary font-bold px-4 py-2 rounded text-xs hover:scale-105 active:scale-95 transition-all"
                      >
                        Check Eligibility
                      </button>
                    </div>
                    <div className="absolute -right-8 -bottom-8 opacity-20 transition-transform group-hover:scale-110 duration-500">
                      <Home className="w-24 h-24 text-white" />
                    </div>
                  </div>

                </div>

                {/* Right side: Recent Transactions block */}
                <div className="lg:col-span-2 space-y-4">
                  <div className="flex justify-between items-center">
                    <h3 className="font-headline text-lg font-bold text-on-surface">Recent Transactions</h3>
                    <div className="flex gap-2 text-xs">
                      <button 
                        onClick={() => setTransactionLimit(5)}
                        className={`px-2.5 py-1 rounded font-semibold ${transactionLimit === 5 ? "bg-primary text-white" : "bg-slate-100 text-slate-600"}`}
                      >
                        5 records
                      </button>
                      <button 
                        onClick={() => setTransactionLimit(10)}
                        className={`px-2.5 py-1 rounded font-semibold ${transactionLimit === 10 ? "bg-primary text-white" : "bg-slate-100 text-slate-600"}`}
                      >
                        10 records
                      </button>
                    </div>
                  </div>

                  {/* Transactions Table block */}
                  <div className="bg-white border border-outline-variant rounded-xl overflow-hidden shadow-sm">
                    
                    {/* Table search bar header */}
                    <div className="px-5 py-4 border-b border-outline-variant flex flex-wrap justify-between items-center gap-3 bg-slate-50/50">
                      <div className="relative w-full max-w-xs">
                        <span className="absolute left-3 top-1/2 -translate-y-1/2">
                          <Search className="w-4 h-4 text-slate-400" />
                        </span>
                        <input 
                          type="text" 
                          placeholder="Search transactions..."
                          value={searchQuery}
                          onChange={(e) => setSearchQuery(e.target.value)}
                          className="pl-9 pr-4 py-2 bg-white border border-outline-variant rounded-full text-xs focus:border-primary outline-none w-full"
                        />
                      </div>
                      <button className="flex items-center gap-1 text-xs font-semibold text-slate-500 hover:text-primary transition-colors">
                        <Filter className="w-3.5 h-3.5" />
                        <span>Filter list</span>
                      </button>
                    </div>

                    {/* Table content */}
                    <div className="overflow-x-auto">
                      <table className="w-full text-left border-collapse text-xs">
                        <thead>
                          <tr className="bg-slate-100/50 border-b border-outline-variant text-slate-500 font-semibold">
                            <th className="px-5 py-3 font-semibold uppercase">Date</th>
                            <th className="px-5 py-3 font-semibold uppercase">Description</th>
                            <th className="px-5 py-3 font-semibold uppercase text-right">Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-outline-variant font-medium">
                          {filteredTransactions.length === 0 ? (
                            <tr>
                              <td colSpan={3} className="px-5 py-8 text-center text-slate-400">
                                No matching transactions found.
                              </td>
                            </tr>
                          ) : (
                            filteredTransactions.map((tx, idx) => (
                              <tr key={idx} className="hover:bg-slate-50 transition-colors">
                                <td className="px-5 py-4 text-slate-400 whitespace-nowrap">{tx.date}</td>
                                <td className="px-5 py-4">
                                  <div className="flex flex-col">
                                    <span className="font-bold text-slate-900">{tx.description}</span>
                                    <span className="text-[10px] text-slate-400">{tx.type}</span>
                                  </div>
                                </td>
                                <td className={`px-5 py-4 text-right font-bold text-sm whitespace-nowrap ${tx.is_credit ? "text-emerald-700" : "text-rose-700"}`}>
                                  {tx.amount}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>

                    {/* Pagination */}
                    <div className="px-5 py-3 bg-slate-50 border-t border-outline-variant flex items-center justify-between text-slate-400 text-[11px]">
                      <span>Showing {filteredTransactions.length} transaction entries</span>
                      <span className="font-bold text-primary">Secured via RAM Encryption</span>
                    </div>

                  </div>
                </div>

              </div>

            </main>
          </div>
        </div>
      )}


      {/* ----------------- BRAND FOOTER ----------------- */}
      <footer className="bg-surface-container-lowest border-t border-outline-variant py-6 mt-auto z-10">
        <div className="flex flex-col md:flex-row justify-between items-center px-6 md:px-10 max-w-7xl mx-auto gap-4 text-xs">
          <div className="flex flex-col items-center md:items-start">
            <span className="font-bold text-primary">Heritage Trust Bank Ltd.</span>
            <p className="text-on-surface-variant mt-1">© 2024 Heritage Trust Bank Ltd. Licensed by RBI.</p>
          </div>
          
          <div className="flex flex-wrap justify-center gap-6">
            <a className="text-on-surface-variant hover:text-primary hover:underline transition-all" href="#">Privacy Policy</a>
            <a className="text-on-surface-variant hover:text-primary hover:underline transition-all" href="#">Terms of Service</a>
            <a className="text-on-surface-variant hover:text-primary hover:underline transition-all" href="#">Security Tips</a>
            <a className="text-on-surface-variant hover:text-primary hover:underline transition-all" href="#">Contact Us</a>
          </div>

          <div className="flex items-center gap-2 text-primary font-bold">
            <Smartphone className="w-4 h-4" />
            <span>1800-HTB-SECURE</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
