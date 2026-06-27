import React, { useState, useEffect } from 'react';
import { Smartphone, Shield, Code, Cpu, LogOut, RefreshCw, Radio } from 'lucide-react';
import { AndroidActivity, BehaviorMetrics, SecurityScores, ConsoleLogEntry, ClientRequest, ClientResponse } from './types';

// Component Imports
import AndroidEmulator from './components/AndroidEmulator';
import SidebarPanel from './components/SidebarPanel';
import CodeViewer from './components/CodeViewer';
import ConsoleLog from './components/ConsoleLog';

// Activities
import LoginActivity from './components/activities/LoginActivity';
import DashboardActivity from './components/activities/DashboardActivity';
import TransferActivity from './components/activities/TransferActivity';
import TransferSuccessActivity from './components/activities/TransferSuccessActivity';
import SecurityCenterActivity from './components/activities/SecurityCenterActivity';
import TransactionHistoryActivity from './components/activities/TransactionHistoryActivity';

export default function App() {
  // Simulator State
  const [activity, setActivity] = useState<AndroidActivity>('LoginActivity');
  const [logs, setLogs] = useState<ConsoleLogEntry[]>([]);
  
  // Real-time API Payload Inspectors
  const [activeRequest, setActiveRequest] = useState<ClientRequest | null>(null);
  const [activeResponse, setActiveResponse] = useState<ClientResponse | null>(null);

  // Behavioral Metrics (Default to Legitimate Rohan S.)
  const [metrics, setMetrics] = useState<BehaviorMetrics>({
    typingSpeed: 142,
    flightTimeVariance: 18,
    holdTime: 82,
    tremorFreq: 2.1,
    deviceAngle: 42,
    aeReconError: 1.25,
    activeCall: false
  });

  // Security Scores extra calculations
  const [scores, setScores] = useState<SecurityScores>({
    trustScore: 0.98,
    behaviorMatchScore: 0.96,
    deviceTrust: 0.98,
    qualitativeState: 'Protected'
  });

  // Success flow storage parameters (rendered without double fetches)
  const [transferParams, setTransferParams] = useState<{ amount: number; beneficiaryName: string } | null>(null);

  // Helper logging utility
  const logEvent = (
    tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', 
    message: string, 
    level: 'info' | 'warning' | 'error' | 'success' = 'info'
  ) => {
    const d = new Date();
    const timestamp = d.toLocaleTimeString('en-US', { hour12: false }) + '.' + String(d.getMilliseconds()).padStart(3, '0');
    const newEntry: ConsoleLogEntry = {
      id: Math.random().toString(36).substring(7),
      timestamp,
      tag,
      message,
      level
    };
    setLogs((prev) => [...prev, newEntry]);
  };

  // Log on app initialization
  useEffect(() => {
    logEvent('CogniGuardClient', 'Initializing mobile edge client SDK', 'success');
    logEvent('TFLiteModel', 'On-device behavioral autoencoder calibrated and ready', 'success');
    logEvent('Activity', 'Launching LoginActivity on device main thread', 'info');
  }, []);

  // Update dynamic SDK API Request / Response models on state change
  useEffect(() => {
    const timestamp = new Date().toISOString();
    if (activity === 'LoginActivity') {
      setActiveRequest({
        endpoint: '/api/v1/auth/login',
        method: 'POST',
        payload: {
          username: 'rohan_heritage',
          behavior: {
            source: 'mobile_edge',
            derived_features: {
              typing_speed: metrics.typingSpeed,
              flight_time_var: metrics.flightTimeVariance,
              tremor_index: Number((metrics.tremorFreq * 0.02).toFixed(4))
            },
            ae_recon_error: Number(metrics.aeReconError.toFixed(2))
          }
        },
        timestamp
      });

      setActiveResponse({
        status: 200,
        payload: {
          action: metrics.aeReconError > 3.5 ? 'verify' : 'allow',
          trust_score: Number((1 - metrics.aeReconError * 0.1).toFixed(2)),
          behavior_match_score: Number((1 - metrics.aeReconError * 0.12).toFixed(2)),
          device_trust: 0.98
        },
        timestamp
      });
    } else if (activity === 'TransferActivity') {
      setActiveRequest({
        endpoint: '/api/v1/payment/score',
        method: 'POST',
        payload: {
          channel: 'mobile', // strictly hardcoded inside SDK
          amount: 12500,
          beneficiary_vpa: 'rohan.saxena@okheritage',
          behavior: {
            source: 'mobile_edge',
            ae_recon_error: Number(metrics.aeReconError.toFixed(2))
          }
        },
        timestamp
      });

      setActiveResponse({
        status: 200,
        payload: {
          action: metrics.activeCall ? 'deny' : 'allow',
          trust_score: metrics.activeCall ? 0.34 : 0.96,
          behavior_match_score: Number((1 - metrics.aeReconError * 0.12).toFixed(2)),
          device_trust: 0.98,
          txn_controls: {
            coercion_warning_required: metrics.activeCall,
            manual_approval_required: metrics.aeReconError > 3.0 && !metrics.activeCall,
            coercion_type: metrics.activeCall ? 'active_call' : undefined,
            limit_coercion_amount: metrics.aeReconError > 3.0 ? 5000 : undefined
          }
        },
        timestamp
      });
    } else {
      setActiveRequest(null);
      setActiveResponse(null);
    }
  }, [activity, metrics]);

  // Handle successful login routing
  const handleLoginSuccess = (scores: SecurityScores) => {
    setScores(scores);
    setActivity('DashboardActivity');
    logEvent('Activity', 'Navigating to DashboardActivity (Home screen)', 'success');
  };

  // Handle successful payment routing
  const handleTransferSuccess = (amount: number, beneficiaryName: string) => {
    setTransferParams({ amount, beneficiaryName });
    setActivity('TransferSuccessActivity');
    logEvent('Activity', `Transfer of ₹${amount} successful. Routing to success screen.`, 'success');
  };

  const handleLogout = () => {
    setActivity('LoginActivity');
    logEvent('Activity', 'User logged out - Clearing active session state', 'warning');
  };

  return (
    <div className="min-h-screen bg-[#f3f4f6] text-slate-800 font-sans antialiased flex flex-col justify-between relative">
      
      {/* Dynamic glow decoration in workspace */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-[#00569c]/5 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-96 h-96 bg-slate-200/40 rounded-full blur-3xl pointer-events-none" />

      {/* Main Workspace Header */}
      <header className="bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between shadow-sm z-10 shrink-0">
        <div className="flex items-center space-x-3">
          <div className="bg-[#00569c]/10 p-2.5 rounded-2xl border border-[#00569c]/15">
            <Smartphone className="w-6 h-6 text-[#00569c]" />
          </div>
          <div className="text-left">
            <h1 className="text-base font-bold tracking-tight text-slate-900">CogniGuard Android Simulator Console</h1>
            <p className="text-xs text-slate-500 mt-0.5">Dual-interface: Interactive phone emulator paired with SDK code tree mapping</p>
          </div>
        </div>

        {/* Global Toolbar */}
        <div className="flex items-center space-x-3">
          <div className="hidden sm:flex items-center space-x-1.5 bg-slate-50 border border-slate-200/80 px-3 py-1.5 rounded-full text-[11px] text-slate-500 shadow-sm">
            <Radio className="w-3.5 h-3.5 text-emerald-600 animate-pulse" />
            <span className="font-semibold text-emerald-600">TFLite Engine Online</span>
          </div>
          {activity !== 'LoginActivity' && (
            <button 
              onClick={handleLogout}
              className="bg-white hover:bg-slate-50 border border-slate-200 p-2 rounded-xl text-slate-400 hover:text-red-600 transition-all cursor-pointer shadow-sm active:scale-95"
              title="Logout"
            >
              <LogOut className="w-4.5 h-4.5" />
            </button>
          )}
        </div>
      </header>

      {/* Main Container Layout split-screen */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6 items-start overflow-hidden">
        
        {/* Left / Main column: Device Frame & Console Logs */}
        <div className="lg:col-span-5 flex flex-col space-y-6">
          
          {/* Simulated Mobile Phone container */}
          <div className="flex justify-center">
            <AndroidEmulator
              activity={activity}
              onBackPress={() => {
                if (activity === 'TransferSuccessActivity' || activity === 'TransferActivity') {
                  setActivity('DashboardActivity');
                  logEvent('Activity', 'Navigating back to DashboardActivity', 'info');
                } else if (activity === 'SecurityCenterActivity' || activity === 'TransactionHistoryActivity') {
                  setActivity('DashboardActivity');
                }
              }}
              onHomePress={() => {
                if (activity !== 'LoginActivity') {
                  setActivity('DashboardActivity');
                  logEvent('Activity', 'Home pressed - Returning to Dashboard', 'info');
                }
              }}
            >
              {/* Dynamic activity renderer mapping based on state */}
              {activity === 'LoginActivity' && (
                <LoginActivity
                  metrics={metrics}
                  onLoginSuccess={handleLoginSuccess}
                  onLog={logEvent}
                />
              )}
              {activity === 'DashboardActivity' && (
                <DashboardActivity
                  scores={scores}
                  onNavigate={(act) => setActivity(act)}
                  onLog={logEvent}
                />
              )}
              {activity === 'TransferActivity' && (
                <TransferActivity
                  metrics={metrics}
                  onBack={() => setActivity('DashboardActivity')}
                  onTransferSuccess={handleTransferSuccess}
                  onLog={logEvent}
                />
              )}
              {activity === 'TransferSuccessActivity' && transferParams && (
                <TransferSuccessActivity
                  amount={transferParams.amount}
                  beneficiaryName={transferParams.beneficiaryName}
                  onBackToHome={() => setActivity('DashboardActivity')}
                  onLog={logEvent}
                />
              )}
              {activity === 'SecurityCenterActivity' && (
                <SecurityCenterActivity
                  metrics={metrics}
                  scores={scores}
                  onBack={() => setActivity('DashboardActivity')}
                  onLog={logEvent}
                />
              )}
              {activity === 'TransactionHistoryActivity' && (
                <TransactionHistoryActivity
                  onBack={() => setActivity('DashboardActivity')}
                  onLog={logEvent}
                />
              )}
            </AndroidEmulator>
          </div>

          {/* Console Log traces box underneath phone */}
          <ConsoleLog
            logs={logs}
            onClear={() => setLogs([])}
          />

        </div>

        {/* Right column: Fine-tuning sliders & Code Editor explorer */}
        <div className="lg:col-span-7 flex flex-col space-y-6">
          
          {/* Sliders panel & Presets */}
          <SidebarPanel
            metrics={metrics}
            scores={scores}
            activeActivity={activity}
            onChangeMetrics={(m) => setMetrics(m)}
            activeRequest={activeRequest}
            activeResponse={activeResponse}
            onLog={logEvent}
          />

          {/* Interactive Kotlin source-code browser */}
          <CodeViewer
            activeTab={activity === 'TransferSuccessActivity' ? 'TransferSuccessActivity' : activity}
          />

        </div>

      </main>

      {/* Footer Branding credits */}
      <footer className="bg-white border-t border-slate-200 px-6 py-4 text-center text-xs text-slate-400 shrink-0 font-sans shadow-sm">
        Heritage Bank Android Simulator with CogniGuard Active Protection. Powered by TFLite On-Device Autoencoder profiling.
      </footer>

    </div>
  );
}
