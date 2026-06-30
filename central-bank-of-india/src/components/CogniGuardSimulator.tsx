/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from "react";
import { Shield, HelpCircle, RefreshCw, Eye, AlertTriangle, CheckCircle, Cpu } from "lucide-react";
import { CogniGuardBehavior } from "../types";

interface CogniGuardSimulatorProps {
  onBehaviorChange: (behavior: CogniGuardBehavior) => void;
  activeBehavior: CogniGuardBehavior;
}

export default function CogniGuardSimulator({ onBehaviorChange, activeBehavior }: CogniGuardSimulatorProps) {
  const [profile, setProfile] = useState<"standard" | "anomalous" | "bot">("standard");

  const applyPreset = (preset: "standard" | "anomalous" | "bot") => {
    setProfile(preset);
    if (preset === "standard") {
      onBehaviorChange({
        profileName: "Standard Owner Profile",
        keystrokeCadence: "steady",
        deviceFingerprint: "Chrome-MacOS-StableFingerprint-9938b",
        locationMatched: true,
        mousePathAnomalies: false,
      });
    } else if (preset === "anomalous") {
      onBehaviorChange({
        profileName: "Anomalous Human Profile",
        keystrokeCadence: "erratic",
        deviceFingerprint: "Firefox-Linux-UnseenDevice-4811a",
        locationMatched: false,
        mousePathAnomalies: true,
      });
    } else {
      onBehaviorChange({
        profileName: "Automated Bot Profile",
        keystrokeCadence: "robotic",
        deviceFingerprint: "HeadlessChrome-Linux-BotFingerprint-0000x",
        locationMatched: false,
        mousePathAnomalies: true,
      });
    }
  };

  return (
    <div className="bg-slate-900 text-slate-100 rounded-xl border border-slate-700 p-6 shadow-xl max-w-sm w-full font-sans transition-all duration-300">
      <div className="flex items-center justify-between border-b border-slate-700 pb-3 mb-4">
        <div className="flex items-center gap-2">
          <Shield className="w-5 h-5 text-emerald-400 animate-pulse" />
          <h2 className="text-md font-bold tracking-tight text-white">CogniGuard™ Inspector</h2>
        </div>
        <span className="text-xs bg-emerald-950 text-emerald-400 px-2 py-0.5 rounded border border-emerald-800 font-mono">
          v4.2 Active
        </span>
      </div>

      <p className="text-xs text-slate-400 mb-4 leading-relaxed">
        CogniGuard tracks millisecond keystroke latency, pointer micro-movements, and device reputations at point of authentication. Use these presets to test adaptive flows:
      </p>

      {/* Preset Buttons */}
      <div className="grid grid-cols-3 gap-2 mb-4">
        <button
          type="button"
          onClick={() => applyPreset("standard")}
          className={`px-2 py-2 rounded text-xs font-semibold border transition-all text-center ${
            profile === "standard"
              ? "bg-emerald-600 border-emerald-400 text-white shadow"
              : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-750"
          }`}
        >
          <CheckCircle className="w-3.5 h-3.5 mx-auto mb-1 text-emerald-200" />
          Steady User
        </button>

        <button
          type="button"
          onClick={() => applyPreset("anomalous")}
          className={`px-2 py-2 rounded text-xs font-semibold border transition-all text-center ${
            profile === "anomalous"
              ? "bg-amber-600 border-amber-400 text-white shadow"
              : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-750"
          }`}
        >
          <HelpCircle className="w-3.5 h-3.5 mx-auto mb-1 text-amber-200" />
          Anomalous
        </button>

        <button
          type="button"
          onClick={() => applyPreset("bot")}
          className={`px-2 py-2 rounded text-xs font-semibold border transition-all text-center ${
            profile === "bot"
              ? "bg-rose-600 border-rose-400 text-white shadow"
              : "bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-750"
          }`}
        >
          <Cpu className="w-3.5 h-3.5 mx-auto mb-1 text-rose-200" />
          Robotic Bot
        </button>
      </div>

      {/* Diagnostic Panel */}
      <div className="bg-slate-950 rounded-lg p-3 border border-slate-800 font-mono text-xs text-slate-300 space-y-2.5">
        <div className="flex justify-between items-center pb-1.5 border-b border-slate-800">
          <span className="text-slate-400">Current Profile:</span>
          <span className={`font-semibold ${
            activeBehavior.keystrokeCadence === "steady" ? "text-emerald-400" :
            activeBehavior.keystrokeCadence === "erratic" ? "text-amber-400" : "text-rose-400"
          }`}>
            {activeBehavior.profileName}
          </span>
        </div>

        <div className="flex justify-between">
          <span className="text-slate-500">Keystroke Cadence:</span>
          <span className="font-semibold text-slate-200 uppercase">{activeBehavior.keystrokeCadence}</span>
        </div>

        <div className="flex justify-between">
          <span className="text-slate-500">Device Signature:</span>
          <span className="font-semibold text-slate-300 overflow-hidden text-ellipsis max-w-[160px] whitespace-nowrap">
            {activeBehavior.deviceFingerprint}
          </span>
        </div>

        <div className="flex justify-between">
          <span className="text-slate-500">Geo-IP Reputation:</span>
          <span className={`font-semibold ${activeBehavior.locationMatched ? "text-emerald-500" : "text-rose-400"}`}>
            {activeBehavior.locationMatched ? "MATCHED (Low Risk)" : "ANOMALOUS (High Risk)"}
          </span>
        </div>

        <div className="flex justify-between">
          <span className="text-slate-500">Interactive Jitter:</span>
          <span className={`font-semibold ${!activeBehavior.mousePathAnomalies ? "text-emerald-500" : "text-amber-400"}`}>
            {activeBehavior.mousePathAnomalies ? "MICRO-STUTTER FLAG" : "NATURAL CURVES"}
          </span>
        </div>

        {/* Visualized Mouse Vector Simulation */}
        <div className="pt-2">
          <p className="text-[10px] text-slate-500 mb-1">Interactive Telemetry Pipeline</p>
          <div className="h-10 bg-slate-900 rounded border border-slate-800 flex items-center justify-center relative overflow-hidden">
            {activeBehavior.keystrokeCadence === "steady" && (
              <svg className="w-full h-full stroke-emerald-500 stroke-2 fill-none" viewBox="0 0 100 40">
                <path d="M0,20 Q15,5 30,20 T60,20 T90,20 L100,20" />
              </svg>
            )}
            {activeBehavior.keystrokeCadence === "erratic" && (
              <svg className="w-full h-full stroke-amber-500 stroke-2 fill-none animate-pulse" viewBox="0 0 100 40">
                <path d="M0,20 L15,10 L30,30 L45,5 L60,35 L75,15 L90,25 L100,20" />
              </svg>
            )}
            {activeBehavior.keystrokeCadence === "robotic" && (
              <svg className="w-full h-full stroke-rose-500 stroke-2 fill-none" viewBox="0 0 100 40">
                <path d="M0,20 H25 V5 H50 V35 H75 V20 H100" />
              </svg>
            )}
            <span className="absolute bottom-1 right-2 text-[8px] text-slate-500">Live Feedback</span>
          </div>
        </div>
      </div>

      <div className="mt-4 flex items-center gap-1.5 text-[11px] text-slate-400">
        <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
        <span>Submitting the login form will dispatch this token package.</span>
      </div>
    </div>
  );
}
