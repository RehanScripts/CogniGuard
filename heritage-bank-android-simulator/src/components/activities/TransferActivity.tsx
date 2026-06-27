import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { ArrowLeft, Search, Plus, Info, Bolt, Landmark, Wallet, QrCode, Send, Fingerprint, ShieldAlert, X, Shield, PhoneCall, Bell } from 'lucide-react';
import { Beneficiary, BehaviorMetrics } from '../../types';
import { MOCK_BENEFICIARIES } from '../../data/mockData';

interface TransferActivityProps {
  metrics: BehaviorMetrics;
  onBack: () => void;
  onTransferSuccess: (amount: number, beneficiaryName: string) => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function TransferActivity({ metrics, onBack, onTransferSuccess, onLog }: TransferActivityProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedPayee, setSelectedPayee] = useState<Beneficiary>(MOCK_BENEFICIARIES[0]);
  const [amount, setAmount] = useState<number>(12500);
  const [method, setMethod] = useState<'IMPS' | 'NEFT' | 'RTGS' | 'UPI'>('IMPS');
  const [remarks, setRemarks] = useState('');

  // UI state overlays triggered by client-side txn_controls state machine
  const [showStepUpBanner, setShowStepUpBanner] = useState(false);
  const [showCoercionPanel, setShowCoercionPanel] = useState(false);
  const [showManualLimitPanel, setShowManualLimitPanel] = useState(false);
  const [isVerifyingBiometric, setIsVerifyingBiometric] = useState(false);
  
  // Step up triggered if amount > 10,000 as per screenshot UI
  useEffect(() => {
    if (amount > 10000) {
      setShowStepUpBanner(true);
    } else {
      setShowStepUpBanner(false);
    }
  }, [amount]);

  const handleSendPayment = (e: React.FormEvent) => {
    e.preventDefault();
    onLog('Activity', `btnSendMoney clicked - Initiating scorePayment on CogniGuard SDK`, 'info');
    onLog('NetworkGateway', `POST /api/v1/payment/score - Channel: "mobile", Amount: ₹${amount}, Beneficiary: ${selectedPayee.vpa}`, 'info');

    // Simulate E5 txn_controls branching
    setTimeout(() => {
      // 1. SCENARIO A: Coercion / Phone scam (simulated by activeCall metrics)
      if (metrics.activeCall) {
        setShowCoercionPanel(true);
        onLog('NetworkGateway', `ALERT - Received Response - Action: DENY_OR_RESOLVE. reason: COERCION_ALERT. Active voice call detected during input.`, 'warning');
        onLog('TFLiteModel', `Behavior autoencoder error is high (${metrics.aeReconError.toFixed(2)}) due to stress-induced typing jitter`, 'warning');
      } 
      // 2. SCENARIO B: Unfamiliar pattern, Moderate autoencoder error
      else if (metrics.aeReconError > 3.0 && amount > 10000) {
        setShowManualLimitPanel(true);
        onLog('NetworkGateway', `ALERT - Received Response - Action: COERCE_LIMIT. reason: BEHAVIOR_DISCREPANCY. Limiting transfer to ₹5,000 safety threshold`, 'warning');
      } 
      // 3. SCENARIO C: Regular Allow
      else {
        onLog('NetworkGateway', `Received Response - Action: ALLOW. trust_score: 0.96. No pending transaction controls.`, 'success');
        onTransferSuccess(amount, selectedPayee.name);
      }
    }, 1000);
  };

  const handleVerifyStepUpBiometric = () => {
    setIsVerifyingBiometric(true);
    onLog('CogniGuardClient', 'Step-up biometric challenge initiated - verifying fingerprint', 'info');
    
    setTimeout(() => {
      setIsVerifyingBiometric(false);
      setShowStepUpBanner(false);
      onLog('TFLiteModel', 'Fingerprint matched. Payment pre-authorization flag set.', 'success');
      onLog('Activity', 'Biometric step-up resolved in-place', 'success');
    }, 1500);
  };

  const resolveCoercionAcknowledge = (scamBypassed: boolean) => {
    setShowCoercionPanel(false);
    if (scamBypassed) {
      onLog('Activity', 'User acknowledged coercion prompt. Force-proceeding with authenticated fingerprint.', 'success');
      onTransferSuccess(amount, selectedPayee.name);
    } else {
      onLog('Activity', 'Payment canceled by user following coercion warn state.', 'error');
      onBack();
    }
  };

  const resolveManualLimitAcknowledge = (acceptLimit: boolean) => {
    setShowManualLimitPanel(false);
    if (acceptLimit) {
      onLog('Activity', 'User accepted safe daily cap limit of ₹5,000.', 'success');
      onTransferSuccess(5000, selectedPayee.name);
    } else {
      onLog('Activity', 'Payment limit adjustment declined.', 'error');
    }
  };

  const filteredPayees = MOCK_BENEFICIARIES.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
    p.vpa.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div id="transfer-activity" className="min-h-full flex flex-col justify-between bg-[#f8f9fa] text-slate-800 relative select-none">
      
      {/* Scrollable container */}
      <div className="flex-1 overflow-y-auto no-scrollbar pb-32">
        
        {/* Top App Bar */}
        <header className="flex items-center justify-between px-4 h-12 sticky top-0 bg-white/90 backdrop-blur-md border-b border-slate-200/85 z-20 shadow-sm">
          <div className="flex items-center space-x-3">
            <button 
              onClick={onBack} 
              className="p-1.5 rounded-full hover:bg-slate-100 text-[#00569c] transition-colors cursor-pointer"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>
            <h1 className="text-sm font-bold font-sans text-slate-850">Transfer</h1>
          </div>
          <div className="flex items-center space-x-2 text-[#00569c]">
            <Landmark className="w-5 h-5" />
            <Bell className="w-5 h-5" />
          </div>
        </header>

        {/* Content Layout */}
        <div className="p-4 space-y-5">
          
          {/* Search Box */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input 
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search name, phone or VPA"
              className="w-full h-12 pl-11 pr-4 bg-white border border-slate-300 rounded-xl text-xs text-slate-800 placeholder:text-slate-400 outline-none focus:border-[#00569c] focus:ring-1 focus:ring-[#00569c] transition-all shadow-sm"
            />
          </div>

          {/* Payee Selection Directory */}
          <section className="space-y-2">
            <div className="flex overflow-x-auto no-scrollbar gap-4 py-1">
              
              {/* Add New */}
              <div className="flex flex-col items-center gap-1.5 min-w-[64px] cursor-pointer">
                <button 
                  type="button"
                  onClick={() => onLog('Activity', 'Add New Payee modal triggered', 'info')}
                  className="w-12 h-12 rounded-full border-2 border-dashed border-[#00569c] flex items-center justify-center text-[#00569c] active:scale-95 transition-transform bg-white"
                >
                  <Plus className="w-5 h-5" />
                </button>
                <span className="text-[10px] font-semibold text-slate-500">Add New</span>
              </div>

              {/* Recents list */}
              {filteredPayees.map((payee) => {
                const isSelected = selectedPayee.id === payee.id;
                return (
                  <div 
                    key={payee.id}
                    onClick={() => {
                      setSelectedPayee(payee);
                      onLog('Activity', `Selected Payee: ${payee.name} (${payee.vpa})`, 'info');
                    }}
                    className="flex flex-col items-center gap-1.5 min-w-[64px] cursor-pointer"
                  >
                    <div className={`w-12 h-12 rounded-full p-0.5 transition-all ${
                      isSelected ? 'ring-2 ring-[#00569c] ring-offset-2 ring-offset-[#f8f9fa]' : 'opacity-70 grayscale'
                    }`}>
                      <img 
                        src={payee.avatar} 
                        alt={payee.name} 
                        className="w-full h-full object-cover rounded-full bg-slate-100"
                        referrerPolicy="no-referrer"
                      />
                    </div>
                    <span className={`text-[10px] font-semibold ${isSelected ? 'text-[#00569c] font-bold' : 'text-slate-500'}`}>
                      {payee.name}
                    </span>
                  </div>
                );
              })}

            </div>
          </section>

          {/* Amount Field Editor */}
          <section className="text-center py-4 bg-white rounded-2xl border border-slate-200 shadow-sm relative">
            <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Enter Amount</span>
            <div className="flex items-center justify-center mt-2 space-x-1">
              <span className="text-3xl font-bold text-[#00569c]">₹</span>
              <input 
                type="number"
                value={amount || ''}
                onChange={(e) => setAmount(Number(e.target.value))}
                className="w-36 bg-transparent border-none text-center text-3xl font-bold text-slate-800 focus:ring-0 p-0 outline-none"
                placeholder="0"
              />
            </div>
            
            {/* Daily limit alert badge */}
            <div className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-50 border border-slate-200/80 rounded-full mt-4 text-[10px] text-slate-500 shadow-sm">
              <Info className="w-3.5 h-3.5 text-[#00569c]" />
              <span>Daily limit: ₹50,000</span>
            </div>
          </section>

          {/* Transfer Type Chips */}
          <section className="space-y-3">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-1 text-left">Payment Method</h3>
            <div className="grid grid-cols-2 gap-2">
              
              <button 
                type="button"
                onClick={() => setMethod('IMPS')}
                className={`flex items-center justify-center gap-1.5 h-11 rounded-xl border text-xs font-semibold active:scale-95 transition-all cursor-pointer ${
                  method === 'IMPS' 
                    ? 'border-[#00569c] bg-[#00569c]/10 text-[#00569c] shadow-sm font-bold' 
                    : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm'
                }`}
              >
                <Bolt className="w-4 h-4" />
                <span>IMPS</span>
              </button>

              <button 
                type="button"
                onClick={() => setMethod('NEFT')}
                className={`flex items-center justify-center gap-1.5 h-11 rounded-xl border text-xs font-semibold active:scale-95 transition-all cursor-pointer ${
                  method === 'NEFT' 
                    ? 'border-[#00569c] bg-[#00569c]/10 text-[#00569c] shadow-sm font-bold' 
                    : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm'
                }`}
              >
                <Landmark className="w-4 h-4" />
                <span>NEFT</span>
              </button>

              <button 
                type="button"
                onClick={() => setMethod('RTGS')}
                className={`flex items-center justify-center gap-1.5 h-11 rounded-xl border text-xs font-semibold active:scale-95 transition-all cursor-pointer ${
                  method === 'RTGS' 
                    ? 'border-[#00569c] bg-[#00569c]/10 text-[#00569c] shadow-sm font-bold' 
                    : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm'
                }`}
              >
                <Wallet className="w-4 h-4" />
                <span>RTGS</span>
              </button>

              <button 
                type="button"
                onClick={() => setMethod('UPI')}
                className={`flex items-center justify-center gap-1.5 h-11 rounded-xl border text-xs font-semibold active:scale-95 transition-all cursor-pointer ${
                  method === 'UPI' 
                    ? 'border-[#00569c] bg-[#00569c]/10 text-[#00569c] shadow-sm font-bold' 
                    : 'border-slate-200 bg-white hover:bg-slate-50 text-slate-700 shadow-sm'
                }`}
              >
                <QrCode className="w-4 h-4" />
                <span>UPI</span>
              </button>

            </div>
          </section>

          {/* Remarks input */}
          <section className="space-y-1">
            <label className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-1 text-left block">Remarks (Optional)</label>
            <input 
              type="text"
              value={remarks}
              onChange={(e) => setRemarks(e.target.value)}
              placeholder="Rent, Dinner, Gift etc."
              className="w-full h-12 px-4 bg-white border border-slate-300 rounded-xl text-xs text-slate-800 focus:border-[#00569c] focus:ring-1 focus:ring-[#00569c] outline-none shadow-sm"
            />
          </section>

        </div>
      </div>

      {/* Fixed Bottom Action Container */}
      <div className="absolute bottom-0 left-0 right-0 bg-white/95 backdrop-blur-md p-4 border-t border-slate-200/80 z-30 shadow-[0_-4px_12px_rgba(0,0,0,0.03)]">
        
        {/* Step-up fingerprint Verification Snackbar (Dynamic on Amount > 10,000) */}
        <AnimatePresence>
          {showStepUpBanner && (
            <motion.div 
              initial={{ y: 20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: 20, opacity: 0 }}
              className="mb-3"
            >
              <div className="bg-red-50 text-slate-800 p-3.5 rounded-xl border border-red-200 shadow-lg flex items-center justify-between gap-3 relative overflow-hidden">
                <div className="flex items-center space-x-3 text-left">
                  <button 
                    onClick={handleVerifyStepUpBiometric}
                    disabled={isVerifyingBiometric}
                    className="bg-red-500 w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0 text-white cursor-pointer hover:scale-105 transition-transform"
                  >
                    {isVerifyingBiometric ? (
                      <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                    ) : (
                      <Fingerprint className="w-5 h-5" />
                    )}
                  </button>
                  <div>
                    <p className="text-xs font-bold text-red-900">Step-up Verification</p>
                    <p className="text-[10px] text-red-700 mt-0.5">Biometric pre-auth needed for payments &gt; ₹10,000</p>
                  </div>
                </div>
                <button 
                  onClick={() => setShowStepUpBanner(false)}
                  className="text-slate-400 hover:text-slate-700 cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
 
        {/* Send Money Trigger Button */}
        <button 
          onClick={handleSendPayment}
          disabled={!amount}
          className="w-full h-12 bg-[#00569c] hover:bg-[#004b87] text-white font-bold text-sm rounded-full flex items-center justify-center gap-2 active:scale-98 transition-transform cursor-pointer disabled:opacity-50"
        >
          <Send className="w-4 h-4 rotate-[-15deg]" />
          <span>Send Money</span>
        </button>
      </div>

      {/* Security Coercion Sheet (txn_controls State Machine) */}
      <AnimatePresence>
        {showCoercionPanel && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/40 z-40"
            />
            <motion.div 
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              className="absolute bottom-0 left-0 right-0 bg-white border-t border-red-200 rounded-t-3xl z-50 p-5 shadow-2xl"
            >
              <div className="w-full flex justify-center pb-4">
                <div className="w-8 h-1 bg-red-100 rounded-full" />
              </div>

              <div className="flex items-center gap-3 mb-4 text-left">
                <div className="w-11 h-11 rounded-full bg-red-50 border border-red-100 flex items-center justify-center text-red-600">
                  <PhoneCall className="w-5 h-5 animate-bounce" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">Active Coercion Warning</h3>
                  <p className="text-[9px] text-red-600 font-bold tracking-wider uppercase mt-0.5">Critical Behavioral Intercept</p>
                </div>
              </div>

              <div className="bg-red-50 border border-red-100 rounded-xl p-3 mb-4 text-[11px] text-red-800 leading-relaxed flex items-start gap-2 text-left">
                <ShieldAlert className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-600" />
                <div>
                  <p className="font-bold">Active Voice Call Detected</p>
                  <p className="opacity-90 mt-0.5">We detected an active phone call during keyboard entries. Scammers frequently instruct victims over phone lines.</p>
                </div>
              </div>

              <p className="text-xs text-slate-600 leading-relaxed mb-6 text-left">
                Are you being told by a caller (e.g., claiming to be bank staff, tech support, or police) to make this transfer?
              </p>

              <div className="flex flex-col gap-2.5">
                <button 
                  onClick={() => resolveCoercionAcknowledge(false)}
                  className="w-full h-11 bg-red-600 hover:bg-red-700 text-white text-xs font-semibold rounded-full cursor-pointer shadow-sm"
                >
                  No, I am Safe (Stop & Cancel Transfer)
                </button>
                <button 
                  onClick={() => resolveCoercionAcknowledge(true)}
                  className="w-full h-11 border border-slate-200 text-xs font-semibold rounded-full text-slate-600 hover:text-slate-800 hover:bg-slate-50 cursor-pointer bg-white"
                >
                  I Authenticate Voice (Proceed with Fingerprint)
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

      {/* Manual Limit Adjustment Sheet (txn_controls limit Restrict) */}
      <AnimatePresence>
        {showManualLimitPanel && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 0.4 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 bg-slate-900/40 z-40"
            />
            <motion.div 
              initial={{ y: '100%' }}
              animate={{ y: 0 }}
              exit={{ y: '100%' }}
              className="absolute bottom-0 left-0 right-0 bg-white border-t border-blue-100 rounded-t-3xl z-50 p-5 shadow-2xl"
            >
              <div className="w-full flex justify-center pb-4">
                <div className="w-8 h-1 bg-slate-200 rounded-full" />
              </div>

              <div className="flex items-center gap-3 mb-4 text-left">
                <div className="w-11 h-11 rounded-full bg-blue-50 flex items-center justify-center text-[#00569c]">
                  <Shield className="w-5 h-5 fill-[#00569c]/10" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">Anomalous Limit Cap</h3>
                  <p className="text-[9px] text-[#00569c] font-bold tracking-wider uppercase mt-0.5">Automated Risk Mitigation</p>
                </div>
              </div>

              <div className="bg-blue-50 border border-blue-100 rounded-xl p-3 mb-4 text-[11px] text-[#00569c] leading-relaxed text-left">
                <p className="font-bold">Transfer Restricted to ₹5,000</p>
                <p className="opacity-90 mt-0.5">Your on-device typing rhythms show a moderate mismatch from your verified profile. For safety, this payment is capped.</p>
              </div>

              <div className="flex flex-col gap-2.5">
                <button 
                  onClick={() => resolveManualLimitAcknowledge(true)}
                  className="w-full h-11 bg-[#00569c] hover:bg-[#004b87] text-white text-xs font-semibold rounded-full cursor-pointer shadow-sm"
                >
                  Accept Adjusted Limit (₹5,000)
                </button>
                <button 
                  onClick={() => resolveManualLimitAcknowledge(false)}
                  className="w-full h-11 border border-slate-200 text-xs font-semibold rounded-full text-slate-500 hover:text-slate-800 hover:bg-slate-50 cursor-pointer bg-white"
                >
                  Cancel Transaction
                </button>
              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>

    </div>
  );
}
