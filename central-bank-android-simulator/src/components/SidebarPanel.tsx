import React, { useState, useEffect } from 'react';
import { Settings2, Zap, PhoneCall, Sliders, ShieldAlert, FileJson, Check, Copy } from 'lucide-react';
import { BehaviorMetrics, SecurityScores, ClientRequest, ClientResponse } from '../types';

interface SidebarPanelProps {
  metrics: BehaviorMetrics;
  scores: SecurityScores;
  activeActivity: string;
  onChangeMetrics: (newMetrics: BehaviorMetrics) => void;
  activeRequest: ClientRequest | null;
  activeResponse: ClientResponse | null;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function SidebarPanel({
  metrics,
  scores,
  activeActivity,
  onChangeMetrics,
  activeRequest,
  activeResponse,
  onLog
}: SidebarPanelProps) {
  const [selectedPreset, setSelectedPreset] = useState<'legit' | 'takeover' | 'coerced'>('legit');
  const [copiedReq, setCopiedReq] = useState(false);
  const [copiedRes, setCopiedRes] = useState(false);

  const presets = {
    legit: {
      name: 'Legitimate Rohan',
      desc: 'Owner typing cadence. Low reconstruction error. Safe allow.',
      metrics: {
        typingSpeed: 142,
        flightTimeVariance: 18,
        holdTime: 82,
        tremorFreq: 2.1,
        deviceAngle: 42,
        aeReconError: 1.25,
        activeCall: false
      }
    },
    takeover: {
      name: 'Account Takeover Threat',
      desc: 'Anomalous typing gestures. High reconstruction error. Triggers Login verify.',
      metrics: {
        typingSpeed: 230,
        flightTimeVariance: 48,
        holdTime: 125,
        tremorFreq: 6.8,
        deviceAngle: 15,
        aeReconError: 4.85,
        activeCall: false
      }
    },
    coerced: {
      name: 'Coerced / Scammed User',
      desc: 'Caller instructing payee over active line. Triggers coercion panel.',
      metrics: {
        typingSpeed: 95,
        flightTimeVariance: 32,
        holdTime: 95,
        tremorFreq: 4.2,
        deviceAngle: 45,
        aeReconError: 2.95,
        activeCall: true
      }
    }
  };

  const applyPreset = (presetKey: 'legit' | 'takeover' | 'coerced') => {
    setSelectedPreset(presetKey);
    const selected = presets[presetKey];
    onChangeMetrics(selected.metrics);
    onLog('CogniGuardClient', `Simulated preset activated: ${selected.name}`, 'info');
    onLog('TFLiteModel', `Loaded reconstruction profile: Error cap set to ${selected.metrics.aeReconError.toFixed(2)}`, 'info');
  };

  const handleSliderChange = (key: keyof BehaviorMetrics, value: number | boolean) => {
    const updated = { ...metrics, [key]: value };
    
    // Automatically derive preset matching
    if (key === 'aeReconError' || key === 'activeCall') {
      setSelectedPreset('legit'); // Reset selected state to represent custom adjustments
    }

    onChangeMetrics(updated);
  };

  const handleCopyJson = (obj: any, setCopied: (v: boolean) => void) => {
    if (!obj) return;
    navigator.clipboard.writeText(JSON.stringify(obj, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-5">
      
      {/* Preset configurations */}
      <section className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-850 mb-3">
          <Zap className="w-4 h-4 text-[#00569c]" />
          <h3 className="tracking-wide uppercase font-sans">Behavioral Security Presets</h3>
        </div>
        
        <div className="space-y-2.5">
          {Object.entries(presets).map(([key, value]) => {
            const isSelected = selectedPreset === key;
            return (
              <button
                key={key}
                onClick={() => applyPreset(key as any)}
                className={`w-full text-left p-3 rounded-xl border transition-all cursor-pointer ${
                  isSelected 
                    ? 'bg-[#00569c]/10 border-[#00569c] shadow-xs' 
                    : 'bg-white border-slate-200 hover:border-slate-350 hover:bg-slate-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-bold ${isSelected ? 'text-[#00569c] font-bold' : 'text-slate-800'}`}>
                    {value.name}
                  </span>
                  {value.metrics.activeCall && (
                    <span className="inline-flex items-center gap-1 text-[8px] bg-red-50 text-red-600 font-bold px-1.5 py-0.5 rounded border border-red-100">
                      <PhoneCall className="w-2.5 h-2.5" />
                      <span>Caller</span>
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-slate-500 mt-1 leading-normal font-medium">
                  {value.desc}
                </p>
              </button>
            );
          })}
        </div>
      </section>

      {/* Manual Fine-Tuning Metric Sliders */}
      <section className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-855 mb-4">
          <Sliders className="w-4 h-4 text-[#00569c]" />
          <h3 className="tracking-wide uppercase font-sans">Metric Fine-Tuning</h3>
        </div>

        <div className="space-y-4">
          
          {/* TFLite Reconstruction Error */}
          <div className="space-y-1.5 text-left">
            <div className="flex justify-between text-xs font-semibold">
              <span className="text-slate-750">TFLite Autoencoder Error</span>
              <span className={`font-mono font-bold ${metrics.aeReconError > 3.5 ? 'text-red-550' : 'text-emerald-600'}`}>
                {metrics.aeReconError.toFixed(2)}
              </span>
            </div>
            <input 
              type="range"
              min="0.5"
              max="10"
              step="0.05"
              value={metrics.aeReconError}
              onChange={(e) => handleSliderChange('aeReconError', parseFloat(e.target.value))}
              className="w-full accent-[#00569c] cursor-pointer bg-slate-150 h-1.5 rounded-lg appearance-none border border-slate-200"
            />
            <div className="flex justify-between text-[8px] text-slate-400 font-bold">
              <span>0.5 (Owner Match)</span>
              <span>10.0 (Extreme Threat)</span>
            </div>
          </div>

          {/* Call Active Switch */}
          <div className="flex items-center justify-between p-2 bg-slate-50 border border-slate-200/65 rounded-xl">
            <div className="flex items-center space-x-2">
              <PhoneCall className={`w-4 h-4 ${metrics.activeCall ? 'text-red-500 animate-pulse' : 'text-slate-400'}`} />
              <div className="text-left">
                <p className="text-xs font-semibold text-slate-800">Simulate Active Caller</p>
                <p className="text-[9px] text-slate-400 font-medium">Interferes with social engineering score</p>
              </div>
            </div>
            <button 
              onClick={() => handleSliderChange('activeCall', !metrics.activeCall)}
              className={`w-11 h-6 rounded-full p-1 transition-colors cursor-pointer ${
                metrics.activeCall ? 'bg-red-500' : 'bg-slate-200'
              }`}
            >
              <div className={`w-4 h-4 bg-white rounded-full transition-transform ${
                metrics.activeCall ? 'translate-x-5' : 'translate-x-0'
              }`} />
            </button>
          </div>

        </div>
      </section>

      {/* SDK API Contract Inspectors */}
      <section className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm space-y-4">
        
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-850">
          <FileJson className="w-4 h-4 text-[#00569c]" />
          <h3 className="tracking-wide uppercase font-sans">SDK Live API Payload Inspector</h3>
        </div>

        {/* Request payload */}
        <div className="space-y-1.5 text-left">
          <div className="flex justify-between items-center text-[10px] font-bold text-slate-400 uppercase tracking-wider pl-1">
            <span>SDK API Request ({activeRequest?.method || 'POST'})</span>
            {activeRequest && (
              <button 
                onClick={() => handleCopyJson(activeRequest, setCopiedReq)}
                className="text-[9px] text-[#00569c] flex items-center space-x-1 hover:underline cursor-pointer"
              >
                {copiedReq ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                <span>{copiedReq ? 'Copied' : 'Copy'}</span>
              </button>
            )}
          </div>
          <div className="bg-slate-950 border border-slate-900 rounded-xl p-3 h-32 overflow-y-auto font-mono text-[9px] no-scrollbar">
            {activeRequest ? (
              <pre className="text-purple-300">
                {JSON.stringify(activeRequest.payload, null, 2)}
              </pre>
            ) : (
              <span className="text-slate-650 italic">Waiting for activity action...</span>
            )}
          </div>
        </div>

        {/* Response payload */}
        <div className="space-y-1.5 text-left">
          <div className="flex justify-between items-center text-[10px] font-bold text-slate-400 uppercase tracking-wider pl-1">
            <span>Server Response (HTTP {activeResponse?.status || '200'})</span>
            {activeResponse && (
              <button 
                onClick={() => handleCopyJson(activeResponse, setCopiedRes)}
                className="text-[9px] text-[#00569c] flex items-center space-x-1 hover:underline cursor-pointer"
              >
                {copiedRes ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                <span>{copiedRes ? 'Copied' : 'Copy'}</span>
              </button>
            )}
          </div>
          <div className="bg-slate-950 border border-slate-900 rounded-xl p-3 h-32 overflow-y-auto font-mono text-[9px] no-scrollbar">
            {activeResponse ? (
              <pre className="text-emerald-400">
                {JSON.stringify(activeResponse.payload, null, 2)}
              </pre>
            ) : (
              <span className="text-slate-650 italic">Waiting for server callback...</span>
            )}
          </div>
        </div>

      </section>

    </div>
  );
}
