import React, { useEffect, useRef } from 'react';
import { Terminal, Shield, Cpu, RefreshCw, AlertCircle } from 'lucide-react';
import { ConsoleLogEntry } from '../types';

interface ConsoleLogProps {
  logs: ConsoleLogEntry[];
  onClear: () => void;
}

export default function ConsoleLog({ logs, onClear }: ConsoleLogProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Scroll to bottom whenever new logs are appended
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  const getTagColor = (tag: string) => {
    switch (tag) {
      case 'CogniGuardClient': return 'text-[#00569c] bg-[#00569c]/10';
      case 'TFLiteModel': return 'text-amber-700 bg-amber-50';
      case 'Activity': return 'text-indigo-700 bg-indigo-50';
      case 'NetworkGateway': return 'text-emerald-700 bg-emerald-50';
      default: return 'text-slate-500 bg-slate-100';
    }
  };

  const getLevelColor = (level: string) => {
    switch (level) {
      case 'success': return 'text-emerald-600 font-bold';
      case 'warning': return 'text-amber-600 font-bold';
      case 'error': return 'text-red-650 font-bold';
      default: return 'text-slate-700';
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl flex flex-col h-44 overflow-hidden shadow-sm">
      
      {/* Logger Header */}
      <div className="bg-slate-50/50 px-4 py-2 flex items-center justify-between border-b border-slate-200/80">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-800">
          <Terminal className="w-4 h-4 text-[#00569c]" />
          <span className="font-mono tracking-wider">Device Runtime Console Logs</span>
        </div>
        <button 
          onClick={onClear}
          className="text-[10px] bg-white hover:bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-slate-500 hover:text-slate-800 font-mono transition-colors cursor-pointer shadow-xs"
        >
          Clear Logs
        </button>
      </div>

      {/* Logs Scroll container */}
      <div 
        ref={containerRef} 
        className="flex-1 overflow-y-auto p-3 font-mono text-[10px] space-y-2.5 leading-normal no-scrollbar bg-white"
      >
        {logs.map((log) => (
          <div key={log.id} className="flex items-start space-x-2 border-l border-slate-200 pl-2">
            
            {/* Timestamp */}
            <span className="text-slate-400 select-none shrink-0">{log.timestamp}</span>
 
            {/* Component Tag */}
            <span className={`shrink-0 px-1.5 py-0.5 rounded text-[8px] font-bold tracking-wider uppercase ${getTagColor(log.tag)}`}>
              {log.tag}
            </span>
 
            {/* Level Icon */}
            {log.level === 'warning' && <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />}
            {log.level === 'error' && <AlertCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />}
 
            {/* Message */}
            <span className={`flex-1 text-slate-700 break-all ${getLevelColor(log.level)}`}>
              {log.message}
            </span>

          </div>
        ))}

        {logs.length === 0 && (
          <div className="h-full flex items-center justify-center text-slate-400 italic text-center select-none">
            No system events recorded. Click interactive elements inside the phone to fire.
          </div>
        )}
      </div>

    </div>
  );
}
