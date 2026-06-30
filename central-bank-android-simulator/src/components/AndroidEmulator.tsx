import React, { useState, useEffect } from 'react';
import { Wifi, Signal, Battery, ChevronLeft, Home, Square, ArrowLeft } from 'lucide-react';
import { AndroidActivity, BehaviorMetrics, SecurityScores } from '../types';

interface AndroidEmulatorProps {
  activity: AndroidActivity;
  onBackPress: () => void;
  onHomePress: () => void;
  children: React.ReactNode;
}

export default function AndroidEmulator({
  activity,
  onBackPress,
  onHomePress,
  children
}: AndroidEmulatorProps) {
  const [deviceTime, setDeviceTime] = useState('10:45');

  // Real-time ticking device clock matching timezone
  useEffect(() => {
    const updateTime = () => {
      const d = new Date();
      let hours = d.getHours();
      const minutes = d.getMinutes().toString().padStart(2, '0');
      const ampm = hours >= 12 ? 'PM' : 'AM';
      hours = hours % 12;
      hours = hours ? hours : 12; // the hour '0' should be '12'
      setDeviceTime(`${hours}:${minutes} ${ampm}`);
    };
    updateTime();
    const interval = setInterval(updateTime, 60000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="relative mx-auto w-[330px] h-[670px] bg-slate-800 rounded-[44px] p-2.5 shadow-2xl border-[5.5px] border-slate-700 flex flex-col overflow-hidden select-none">
      
      {/* Front camera punch hole / speaker bar */}
      <div className="absolute top-4 left-1/2 -translate-x-1/2 w-28 h-6 bg-black rounded-full flex items-center justify-between px-3.5 z-40">
        <div className="w-1.5 h-1.5 bg-slate-900 rounded-full" />
        <div className="w-12 h-1 bg-slate-800 rounded-full" />
        <div className="w-1.5 h-1.5 bg-slate-900 rounded-full" />
      </div>

      {/* Simulated top Android Status Bar */}
      <div className="bg-[#f8f9fa] h-6 flex items-center justify-between px-6 text-[10px] font-bold text-slate-500 z-30 font-sans mt-3 shrink-0 border-b border-slate-100">
        <span className="font-semibold text-xs tracking-tight text-slate-700">{deviceTime}</span>
        <div className="flex items-center space-x-1">
          <span className="text-[8px] bg-[#00569c]/10 text-[#00569c] px-1 font-bold rounded shrink-0 scale-90 border border-[#00569c]/15">VoLTE</span>
          <Signal className="w-3 h-3 text-[#00569c]" />
          <Wifi className="w-3.5 h-3.5 text-[#00569c]" />
          <Battery className="w-4 h-4 text-[#00569c] fill-current/20" />
        </div>
      </div>

      {/* Main viewport canvas */}
      <div className="flex-1 bg-[#f8f9fa] relative overflow-hidden rounded-[32px] flex flex-col shadow-inner border border-slate-200">
        
        {/* Render child activity */}
        <div className="flex-1 overflow-hidden h-full">
          {children}
        </div>

        {/* Dynamic Activity Navbar - Persistent footer buttons */}
        {activity !== 'LoginActivity' && (
          <nav className="h-12 bg-[#f8f9fa]/95 border-t border-slate-200/80 flex justify-around items-center absolute bottom-0 left-0 right-0 z-30 shrink-0">
            {/* Home tab button */}
            <button 
              onClick={onHomePress}
              className={`flex flex-col items-center justify-center py-1 px-3.5 rounded-xl transition-all active:scale-95 cursor-pointer ${
                activity === 'DashboardActivity' 
                  ? 'text-[#00569c] bg-[#00569c]/10 font-bold' 
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Home className="w-4.5 h-4.5" />
              <span className="text-[9px] mt-0.5">Home</span>
            </button>

            {/* Transfer tab button */}
            <button 
              onClick={onBackPress}
              className={`flex flex-col items-center justify-center py-1 px-3.5 rounded-xl transition-all active:scale-95 cursor-pointer ${
                activity === 'TransferActivity' || activity === 'TransferSuccessActivity'
                  ? 'text-[#00569c] bg-[#00569c]/10 font-bold' 
                  : 'text-slate-500 hover:text-slate-800'
              }`}
            >
              <Signal className="w-4.5 h-4.5 rotate-45" />
              <span className="text-[9px] mt-0.5">Transfer</span>
            </button>
          </nav>
        )}

      </div>

      {/* Simulated Android System Navigation Drawer Bar (persistent pill handle) */}
      <div className="h-4 bg-slate-800 flex items-center justify-center space-x-12 shrink-0 pt-1">
        <button 
          onClick={onBackPress} 
          disabled={activity === 'LoginActivity' || activity === 'DashboardActivity'}
          className="text-slate-400 hover:text-white disabled:opacity-30 cursor-pointer"
        >
          <ChevronLeft className="w-5 h-5" />
        </button>
        <button 
          onClick={onHomePress}
          disabled={activity === 'LoginActivity'}
          className="w-3.5 h-3.5 border-2 border-slate-400 rounded-full hover:border-white disabled:opacity-30 cursor-pointer"
        />
        <button 
          disabled={activity === 'LoginActivity'}
          className="text-slate-400 disabled:opacity-30 cursor-pointer"
        >
          <Square className="w-3 h-3 rounded" />
        </button>
      </div>

    </div>
  );
}
