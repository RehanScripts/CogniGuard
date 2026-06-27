import React from 'react';
import { motion } from 'motion/react';
import { Check, ShieldCheck, Share2, ArrowRight } from 'lucide-react';

interface TransferSuccessActivityProps {
  amount: number;
  beneficiaryName: string;
  onBackToHome: () => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function TransferSuccessActivity({ amount, beneficiaryName, onBackToHome, onLog }: TransferSuccessActivityProps) {
  // Purely generated locally in-memory
  const mockRefId = React.useMemo(() => 'REF' + Math.floor(100000000000 + Math.random() * 900000000000), []);
  const timestamp = React.useMemo(() => {
    const d = new Date();
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' }) + ', ' + 
           d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
  }, []);

  return (
    <div id="transfer-success-activity" className="min-h-full flex flex-col justify-between bg-[#f8f9fa] text-slate-800 p-5 pt-10 select-none">
      
      {/* Centered Success Box */}
      <div className="flex-1 flex flex-col items-center justify-center text-center space-y-6">
        
        {/* Glowing Success Ring Animation */}
        <div className="relative flex items-center justify-center">
          <motion.div 
            initial={{ scale: 0.5, opacity: 0 }}
            animate={{ scale: [1, 1.3, 1], opacity: [0.4, 0.1, 0.4] }}
            transition={{ repeat: Infinity, duration: 3, ease: 'easeInOut' }}
            className="absolute w-24 h-24 bg-emerald-500/10 rounded-full border border-emerald-500/20"
          />
          <motion.div 
            initial={{ scale: 0.3, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: 'spring', damping: 15 }}
            className="relative w-16 h-16 bg-emerald-500 rounded-full flex items-center justify-center shadow-md shadow-emerald-550/15"
          >
            <Check className="w-8 h-8 text-white stroke-[3px]" />
          </motion.div>
        </div>

        {/* Amount */}
        <div className="space-y-1">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-450">Payment Successful</p>
          <h2 className="text-3xl font-bold font-sans tracking-tight text-slate-850">
            ₹{amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
          </h2>
          <p className="text-xs text-[#00569c] font-semibold">Sent to {beneficiaryName}</p>
        </div>

        {/* Transfer Details Card */}
        <div className="w-full bg-white border border-slate-200 rounded-2xl p-4 text-left divide-y divide-slate-100 shadow-sm">
          <div className="pb-3 flex justify-between text-xs">
            <span className="text-slate-450">Timestamp</span>
            <span className="font-semibold text-slate-800">{timestamp}</span>
          </div>
          <div className="py-3 flex justify-between text-xs">
            <span className="text-slate-450">Reference ID</span>
            <span className="font-mono font-semibold text-slate-800">{mockRefId}</span>
          </div>
          <div className="pt-3 flex justify-between text-xs">
            <span className="text-slate-450">Security Status</span>
            <span className="inline-flex items-center text-emerald-600 font-semibold gap-1">
              <ShieldCheck className="w-4 h-4 fill-emerald-500/10" />
              <span>Protected</span>
            </span>
          </div>
        </div>

        {/* Share Receipt simulated button */}
        <button 
          onClick={() => onLog('Activity', 'Receipt shared successfully', 'success')}
          className="inline-flex items-center space-x-1.5 text-xs text-[#00569c] font-semibold hover:underline cursor-pointer"
        >
          <Share2 className="w-4 h-4" />
          <span>Share e-Receipt</span>
        </button>

      </div>

      {/* Navigation home trigger */}
      <button 
        onClick={() => {
          onLog('Activity', 'Navigating back to DashboardActivity', 'info');
          onBackToHome();
        }}
        className="w-full h-12 bg-[#00569c] hover:bg-[#004b87] text-white font-bold text-sm rounded-full flex items-center justify-center gap-1.5 transition-colors cursor-pointer shadow-md"
      >
        <span>Back to Home</span>
        <ArrowRight className="w-4 h-4" />
      </button>

    </div>
  );
}
