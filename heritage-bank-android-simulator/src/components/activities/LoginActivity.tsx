import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ShieldAlert, Fingerprint, Eye, EyeOff, User, Lock, AlertCircle, X, ShieldCheck } from 'lucide-react';
import { BehaviorMetrics, SecurityScores } from '../../types';

interface LoginActivityProps {
  metrics: BehaviorMetrics;
  onLoginSuccess: (scores: SecurityScores) => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function LoginActivity({ metrics, onLoginSuccess, onLog }: LoginActivityProps) {
  const [username, setUsername] = useState('rohan_heritage');
  const [password, setPassword] = useState('••••••••');
  const [showPassword, setShowPassword] = useState(false);
  const [showConsent, setShowConsent] = useState(false);
  const [consentGranted, setConsentGranted] = useState<boolean | null>(null);
  
  // Step-up verification state (in-place)
  const [isStepUpRequired, setIsStepUpRequired] = useState(false);
  const [isVerifyingBiometric, setIsVerifyingBiometric] = useState(false);
  const [stepUpSuccess, setStepUpSuccess] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Artificial delay to mimic the "first-run" behavioral consent bottom sheet presentation
    const timer = setTimeout(() => {
      if (consentGranted === null) {
        setShowConsent(true);
        onLog('Activity', 'Presenting Behavioral Security bottom-sheet overlay', 'info');
      }
    }, 1000);
    return () => clearTimeout(timer);
  }, [consentGranted]);

  const handleConsent = (granted: boolean) => {
    setConsentGranted(granted);
    setShowConsent(false);
    onLog('CogniGuardClient', `setConsent(${granted}) called - Consent stored locally`, granted ? 'success' : 'warning');
  };

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    if (!username || !password) return;

    setIsLoading(true);
    onLog('Activity', `btnLogin.setOnClickListener triggered - Sending login payload`, 'info');
    onLog('TFLiteModel', `Evaluating on-device keystroke cadence. TFLite Reconstruction Error: ${metrics.aeReconError.toFixed(2)}`, metrics.aeReconError > 3.5 ? 'warning' : 'success');

    setTimeout(() => {
      setIsLoading(false);
      // Determine action branching based on TFLite autoencoder error
      // High reconstruction error (>3.5) means typing speed/cadence deviates from Owner, triggering STEP-UP
      if (metrics.aeReconError > 3.5) {
        setIsStepUpRequired(true);
        onLog('NetworkGateway', `Received Response - Action: VERIFY. Device Trust: 0.92, Overall Trust: 0.45. Triggering in-place step-up.`, 'warning');
      } else {
        // Direct Allow
        const calculatedScores: SecurityScores = {
          trustScore: Math.max(0.1, 1 - (metrics.aeReconError * 0.1) - (metrics.activeCall ? 0.4 : 0)),
          behaviorMatchScore: Math.max(0.1, 1 - (metrics.aeReconError * 0.12)),
          deviceTrust: 0.98,
          qualitativeState: 'Protected'
        };
        onLog('NetworkGateway', `Received Response - Action: ALLOW. Device Trust: ${calculatedScores.deviceTrust}, Behavior Match: ${calculatedScores.behaviorMatchScore.toFixed(2)}`, 'success');
        onLog('Activity', `Passing trust scores to DashboardActivity via Intent Extras`, 'success');
        onLoginSuccess(calculatedScores);
      }
    }, 1200);
  };

  const handleVerifyBiometric = () => {
    setIsVerifyingBiometric(true);
    onLog('CogniGuardClient', 'In-place verifyStepUp biometric callback triggered - Waiting for fingerprint sensor', 'info');
    
    setTimeout(() => {
      setIsVerifyingBiometric(false);
      setStepUpSuccess(true);
      onLog('TFLiteModel', 'Biometric fingerprint signature MATCHED successfully', 'success');
      
      setTimeout(() => {
        const calculatedScores: SecurityScores = {
          trustScore: 0.91,
          behaviorMatchScore: 0.88,
          deviceTrust: 0.98,
          qualitativeState: 'Protected'
        };
        onLog('NetworkGateway', 'Step-up verified. Token authenticated. Navigating to Dashboard.', 'success');
        onLoginSuccess(calculatedScores);
      }, 1000);
    }, 2000);
  };

  return (
    <div id="login-activity" className="relative min-h-full flex flex-col justify-between bg-[#f8f9fa] text-slate-800 p-5 pt-8 select-none">
      
      {/* Scrollable container for forms */}
      <div className="flex-1 flex flex-col justify-center">
        {/* Logo & Brand Header */}
        <div className="flex flex-col items-center mb-10 text-center">
          <div className="w-20 h-20 mb-3 bg-white rounded-2xl flex items-center justify-center border border-slate-200 overflow-hidden shadow-md p-2">
            <img 
              src="https://lh3.googleusercontent.com/aida-public/AB6AXuBOl_VIFV1H7XCMFJ1u5TM8sRrMxZ7i6O1lRgQ2ipAreGL82003NzutBOvtDqXLrNmcDXDd7twIOT1eC4Uxlkk67YQSWt6anulLu4Fs0fj4iQLLtWD7dwLnIWsTtJXUEiSR4biLRGEtq3QIKofY9AFeayiHhNB4FaXR-irC4vUdV5GYwyHVDpkh3qaQwxolILxarrOm0-2qxxCml3VNo8ZByQUMmrisxPowTH81tBoiESvWTGyA0KQtzkNDslCd_5Cp4kw4R1cCfow" 
              alt="Heritage Bank Logo" 
              className="w-full h-full object-contain"
              referrerPolicy="no-referrer"
            />
          </div>
          <h1 className="text-2xl font-bold text-slate-800 tracking-tight font-sans">Heritage Bank</h1>
          <p className="text-xs text-slate-500 mt-1 font-sans">Trust across generations</p>
        </div>

        {/* Action state: Either standard login form OR in-place Step-Up prompt */}
        <AnimatePresence mode="wait">
          {!isStepUpRequired ? (
            <motion.form 
              key="login-form"
              initial={{ opacity: 0, y: 15 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -15 }}
              onSubmit={handleLogin}
              className="space-y-5"
            >
              {/* Username Input */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 pl-1">Username</label>
                <div className="flex items-center bg-white border border-slate-300 rounded-xl px-3 h-12 focus-within:border-[#00569c] focus-within:ring-1 focus-within:ring-[#00569c] transition-all shadow-sm">
                  <User className="text-slate-400 w-5 h-5 mr-2" />
                  <input 
                    type="text" 
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="flex-1 bg-transparent border-none outline-none text-sm text-slate-800 focus:ring-0 placeholder:text-slate-300"
                    placeholder="Enter username"
                    disabled={isLoading}
                  />
                </div>
              </div>

              {/* Password Input */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-500 pl-1">Password</label>
                <div className="flex items-center bg-white border border-slate-300 rounded-xl px-3 h-12 focus-within:border-[#00569c] focus-within:ring-1 focus-within:ring-[#00569c] transition-all shadow-sm">
                  <Lock className="text-slate-400 w-5 h-5 mr-2" />
                  <input 
                    type={showPassword ? 'text' : 'password'} 
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="flex-1 bg-transparent border-none outline-none text-sm text-slate-800 focus:ring-0 placeholder:text-slate-300 tracking-wide"
                    placeholder="Enter password"
                    disabled={isLoading}
                  />
                  <button 
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="text-slate-400 hover:text-slate-700 transition-colors"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              {/* Submit Button */}
              <button 
                type="submit"
                disabled={isLoading}
                className="w-full h-12 bg-[#00569c] hover:bg-[#004b87] text-white font-semibold rounded-full flex items-center justify-center transition-all shadow-md active:scale-98 disabled:opacity-50 mt-6 cursor-pointer"
              >
                {isLoading ? (
                  <div className="flex items-center space-x-2">
                    <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    <span>Securing login...</span>
                  </div>
                ) : (
                  'Login'
                )}
              </button>

              {/* Biometrics & Alternative links */}
              <div className="flex flex-col items-center gap-4 pt-4">
                <button 
                  type="button"
                  onClick={() => {
                    onLog('Activity', 'btnLoginWithBiometrics triggered - launching in-place step up', 'info');
                    setIsStepUpRequired(true);
                  }}
                  className="flex flex-col items-center gap-1.5 active:opacity-75 transition-opacity group cursor-pointer"
                >
                  <div className="w-12 h-12 rounded-full bg-slate-100 border border-slate-200 flex items-center justify-center text-[#00569c] group-hover:bg-[#00569c]/10 transition-colors shadow-sm">
                    <Fingerprint className="w-6 h-6" />
                  </div>
                  <span className="text-xs font-semibold text-[#00569c]">Login with Biometrics</span>
                </button>

                <div className="flex justify-between w-full px-2 text-xs font-semibold text-[#00569c] mt-2">
                  <span className="hover:underline cursor-pointer">Forgot Password?</span>
                  <span className="text-slate-300">|</span>
                  <span className="hover:underline cursor-pointer">Register</span>
                </div>
              </div>
            </motion.form>
          ) : (
            <motion.div 
              key="stepup-prompt"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-white border border-red-200 rounded-3xl p-6 text-center shadow-2xl relative overflow-hidden"
            >
              {/* Red glow backdrop */}
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-40 h-40 bg-red-500/5 rounded-full blur-2xl pointer-events-none" />

              {/* Cancel Button */}
              <button 
                onClick={() => {
                  setIsStepUpRequired(false);
                  onLog('Activity', 'User canceled step-up verification', 'warning');
                }}
                className="absolute top-4 right-4 text-slate-400 hover:text-slate-600 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>

              {/* Security Shield Icon */}
              <div className="inline-flex items-center justify-center mb-6 bg-red-500/10 p-4 rounded-full border border-red-500/20">
                <ShieldAlert className="text-red-500 w-8 h-8 animate-pulse" />
              </div>

              {/* Title & Body */}
              <h2 className="text-lg font-bold text-slate-800 mb-2 font-sans">Confirm with fingerprint</h2>
              <p className="text-xs text-slate-500 max-w-[280px] mx-auto leading-relaxed mb-8">
                An extra security check was triggered due to anomalous keyboard cadence. Place your finger on the sensor to proceed.
              </p>

              {/* Biometric Sensor Area with Ripple Rings */}
              <div className="flex items-center justify-center mb-8 relative">
                <AnimatePresence>
                  {isVerifyingBiometric && (
                    <>
                      <motion.div 
                        initial={{ scale: 0.8, opacity: 0.5 }}
                        animate={{ scale: 2.2, opacity: 0 }}
                        exit={{ scale: 0.8, opacity: 0 }}
                        transition={{ repeat: Infinity, duration: 1.8, ease: "easeOut" }}
                        className="absolute w-20 h-20 rounded-full bg-[#00569c]/20 border border-[#00569c]/30 pointer-events-none"
                      />
                      <motion.div 
                        initial={{ scale: 0.8, opacity: 0.5 }}
                        animate={{ scale: 1.8, opacity: 0 }}
                        exit={{ scale: 0.8, opacity: 0 }}
                        transition={{ repeat: Infinity, duration: 1.8, ease: "easeOut", delay: 0.6 }}
                        className="absolute w-20 h-20 rounded-full bg-[#00569c]/20 border border-[#00569c]/30 pointer-events-none"
                      />
                    </>
                  )}
                </AnimatePresence>

                {/* Fingerprint Button */}
                <button 
                  type="button"
                  onClick={handleVerifyBiometric}
                  disabled={stepUpSuccess}
                  className={`relative z-10 w-20 h-20 rounded-full flex items-center justify-center shadow-lg transition-transform duration-150 cursor-pointer ${
                    stepUpSuccess 
                      ? 'bg-green-500 text-white animate-pulse' 
                      : 'bg-[#00569c] text-white hover:bg-[#004b87] hover:scale-105 active:scale-95'
                  }`}
                >
                  {stepUpSuccess ? (
                    <ShieldCheck className="w-10 h-10 animate-bounce" />
                  ) : (
                    <Fingerprint className="w-10 h-10" />
                  )}
                </button>
              </div>

              {/* Success Overlay message */}
              {stepUpSuccess && (
                <motion.p 
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-sm text-green-600 font-semibold mb-2"
                >
                  Identity Verified Successfully!
                </motion.p>
              )}

              {/* Fallback OTP button */}
              <button 
                type="button"
                onClick={() => {
                  onLog('Activity', 'Fallback to OTP verification requested', 'info');
                }}
                className="w-full h-11 border border-slate-200 hover:border-[#00569c] text-xs text-slate-700 font-semibold rounded-full flex items-center justify-center space-x-1.5 transition-colors cursor-pointer bg-slate-50"
              >
                <span>Use OTP instead</span>
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Footer Version Tag */}
      <footer className="py-4 text-center text-[10px] text-slate-400 font-mono tracking-widest uppercase">
        Secure Connect v4.2.1
      </footer>

      {/* Consent Bottom Sheet Overlay */}
      <AnimatePresence>
        {showConsent && (
          <>
            {/* Scrim Backdrop */}
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              onClick={() => handleConsent(false)}
              className="absolute inset-0 bg-slate-900/60 z-40 cursor-pointer"
            />

            {/* Bottom Sheet Modal */}
            <motion.div 
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              transition={{ type: 'spring', damping: 25, stiffness: 180 }}
              className="absolute bottom-0 left-0 right-0 bg-white border-t border-slate-200 rounded-t-3xl z-50 p-6 shadow-2xl select-none"
            >
              {/* Drag Handle */}
              <div className="w-full flex justify-center pb-4">
                <div className="w-8 h-1 bg-slate-200 rounded-full" />
              </div>

              {/* Icon & Heading */}
              <div className="flex items-center gap-4 mb-4">
                <div className="w-12 h-12 rounded-full bg-[#00569c]/10 flex items-center justify-center text-[#00569c]">
                  <Fingerprint className="w-6 h-6" />
                </div>
                <div className="text-left">
                  <h2 className="text-base font-bold text-slate-800 leading-tight">Enhance your security</h2>
                  <p className="text-[10px] text-[#00569c] font-semibold tracking-wider uppercase mt-0.5">Biometric Consent</p>
                </div>
              </div>

              {/* Body text description */}
              <p className="text-xs text-slate-500 leading-relaxed mb-6 text-left">
                We use on-device behavioral analysis (like how you type and scroll) to protect you from fraud. No personal data is stored—only a unique security profile that helps us verify it's really you.
              </p>

              {/* Consent buttons */}
              <div className="flex flex-col gap-2.5">
                <button 
                  onClick={() => handleConsent(true)}
                  className="w-full h-11 bg-[#00569c] hover:bg-[#004b87] text-white text-xs font-semibold rounded-full active:opacity-90 transition-opacity cursor-pointer shadow-sm"
                >
                  Grant Permission
                </button>
                <button 
                  onClick={() => handleConsent(false)}
                  className="w-full h-11 border border-slate-200 hover:bg-slate-50 text-slate-500 hover:text-slate-800 text-xs font-semibold rounded-full transition-all cursor-pointer bg-white"
                >
                  Decline
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
