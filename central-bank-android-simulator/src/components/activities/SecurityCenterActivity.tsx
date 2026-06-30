import React from 'react';
import { motion } from 'motion/react';
import { ArrowLeft, Shield, ShieldCheck, ShieldAlert, Sparkles, KeyRound, MonitorSmartphone, Settings, Radio } from 'lucide-react';
import { BehaviorMetrics, SecurityScores } from '../../types';

interface SecurityCenterActivityProps {
  metrics: BehaviorMetrics;
  scores: SecurityScores;
  onBack: () => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function SecurityCenterActivity({ metrics, scores, onBack, onLog }: SecurityCenterActivityProps) {
  // Qualitative state mapping based on TFLite reconstruction error and active call state
  const isProtected = metrics.aeReconError <= 3.5 && !metrics.activeCall;

  return (
    <div id="security-center-activity" className="min-h-full flex flex-col bg-[#f8f9fa] text-slate-800 select-none">
      
      {/* Top App Bar */}
      <header className="flex items-center space-x-3 px-4 h-12 border-b border-slate-200/80 sticky top-0 bg-white/90 backdrop-blur-md z-10 shadow-sm">
        <button 
          onClick={onBack} 
          className="p-1.5 rounded-full hover:bg-slate-100 text-[#00569c] cursor-pointer"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-sm font-bold font-sans text-slate-800 font-sans">Security Center</h1>
      </header>

      {/* Main Content Scrollable */}
      <div className="flex-1 overflow-y-auto no-scrollbar p-4 space-y-5 pb-20">
        
        {/* Shield Qualitative Overview Card */}
        <section className="bg-white border border-slate-200 rounded-2xl p-6 text-center relative overflow-hidden shadow-sm">
          
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-32 h-32 bg-[#00569c]/5 rounded-full blur-2xl" />

          {/* Large Shield Display with floating status glow */}
          <div className="flex justify-center mb-4">
            <div className={`p-4 rounded-full border ${
              isProtected 
                ? 'bg-emerald-50 border-emerald-100 text-emerald-600' 
                : 'bg-red-50 border-red-100 text-red-500'
            }`}>
              <Shield className="w-12 h-12 fill-current/10" />
            </div>
          </div>

          {/* Qualitative Status Heading - No raw floats or score numbers displayed */}
          <h2 className="text-lg font-bold text-slate-850 font-sans">
            {isProtected ? 'Protected' : 'Needs attention'}
          </h2>
          
          <p className="text-xs text-slate-500 mt-1.5 max-w-[240px] mx-auto leading-relaxed text-center font-medium">
            {isProtected 
              ? 'Your on-device behavioral lock is active and fully calibrated. No abnormal gestures or threat vectors detected.' 
              : 'On-device profile calibration is in progress, or anomalous stress patterns/active calls are interfering with lock evaluation.'
            }
          </p>

        </section>

        {/* Telemetry settings - Strict Qualitative indicators */}
        <section className="space-y-3">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-1 text-left">Device Guard Parameters</h3>
          
          <div className="bg-white border border-slate-200 rounded-2xl divide-y divide-slate-100 overflow-hidden shadow-sm">
            
            {/* Typing Cadence Lock indicator */}
            <div className="flex items-center justify-between p-4">
              <div className="flex items-center space-x-3 text-left">
                <KeyRound className="w-5 h-5 text-[#00569c]" />
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Typing Cadence Guard</h4>
                  <p className="text-[10px] text-slate-500 mt-0.5">Profiles swipe speed & flight keys</p>
                </div>
              </div>
              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${
                metrics.aeReconError <= 3.5 
                  ? 'bg-emerald-50 text-emerald-600' 
                  : 'bg-amber-50 text-amber-600'
              }`}>
                {metrics.aeReconError <= 3.5 ? 'Calibrated' : 'Drifting Pattern'}
              </span>
            </div>

            {/* Device Hijack Protection */}
            <div className="flex items-center justify-between p-4">
              <div className="flex items-center space-x-3 text-left">
                <MonitorSmartphone className="w-5 h-5 text-[#00569c]" />
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Session Hijack Defense</h4>
                  <p className="text-[10px] text-slate-500 mt-0.5">Guards against hardware takeover</p>
                </div>
              </div>
              <span className="text-[10px] text-emerald-600 font-bold bg-emerald-50 px-2.5 py-1 rounded-full">
                Active
              </span>
            </div>

            {/* Active Coercion sensor */}
            <div className="flex items-center justify-between p-4">
              <div className="flex items-center space-x-3 text-left">
                <Radio className="w-5 h-5 text-[#00569c]" />
                <div>
                  <h4 className="text-xs font-bold text-slate-800">Social Engineering Sensor</h4>
                  <p className="text-[10px] text-slate-500 mt-0.5">Detects active caller instruction pressure</p>
                </div>
              </div>
              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full ${
                !metrics.activeCall 
                  ? 'bg-emerald-50 text-emerald-600' 
                  : 'bg-red-50 text-red-500 animate-pulse'
              }`}>
                {!metrics.activeCall ? 'Clean / Secure' : 'Active Caller Warning'}
              </span>
            </div>

          </div>
        </section>

        {/* Security guidelines disclaimer */}
        <div className="bg-slate-100 border border-slate-200/60 rounded-xl p-3.5 text-[10px] text-slate-500 leading-relaxed text-left">
          <p className="font-bold text-slate-800 mb-1">Qualitative Architecture Note</p>
          In alignment with banking compliance guidelines and SOC data partitions, specific machine learning metrics (including raw reconstruction vectors and weights) are strictly withheld from display and routed only to central verification systems.
        </div>

      </div>
    </div>
  );
}
