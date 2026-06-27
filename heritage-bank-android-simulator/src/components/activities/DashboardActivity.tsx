import React, { useState } from 'react';
import { motion } from 'motion/react';
import { Bell, Search, Eye, EyeOff, Send, History, Receipt, QrCode, CreditCard, ChevronRight, CheckCircle2, AlertTriangle, ArrowUpRight, ArrowDownLeft, Shield, Sparkles } from 'lucide-react';
import { Account, Transaction, SecurityScores } from '../../types';
import { MOCK_ACCOUNTS, MOCK_TRANSACTIONS } from '../../data/mockData';

interface DashboardActivityProps {
  scores: SecurityScores;
  onNavigate: (activity: 'TransferActivity' | 'TransactionHistoryActivity' | 'SecurityCenterActivity') => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function DashboardActivity({ scores, onNavigate, onLog }: DashboardActivityProps) {
  const [hideBalance, setHideBalance] = useState(false);
  const primaryAccount = MOCK_ACCOUNTS[0];

  const handleAction = (activity: 'TransferActivity' | 'TransactionHistoryActivity' | 'SecurityCenterActivity', actionName: string) => {
    onLog('Activity', `Quick Action clicked - Navigating to ${activity} (${actionName})`, 'info');
    onNavigate(activity);
  };

  return (
    <div id="dashboard-activity" className="min-h-full flex flex-col justify-between bg-[#f8f9fa] text-slate-800 select-none">
      
      {/* Scrollable Container */}
      <div className="flex-1 overflow-y-auto no-scrollbar pb-24">
        
        {/* Top Header Bar */}
        <header className="flex items-center justify-between px-4 py-3 sticky top-0 bg-white/90 backdrop-blur-md border-b border-slate-200/80 z-20 shadow-sm">
          <div className="flex items-center space-x-2">
            <span className="text-[#00569c] font-bold text-lg font-mono">HB</span>
            <span className="font-bold text-sm tracking-tight text-slate-800">Heritage Bank</span>
          </div>
          <div className="flex items-center space-x-1">
            <button className="p-2 rounded-full hover:bg-slate-100 text-slate-500 hover:text-slate-800 cursor-pointer">
              <Search className="w-5 h-5" />
            </button>
            <button className="p-2 rounded-full hover:bg-slate-100 text-slate-500 hover:text-slate-800 relative cursor-pointer">
              <Bell className="w-5 h-5" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>
          </div>
        </header>

        {/* Outer margin wrapper */}
        <div className="p-4 space-y-5">
          
          {/* Greeting Section */}
          <section className="flex items-center justify-between">
            <div className="text-left">
              <h2 className="text-xl font-bold text-slate-800 tracking-tight">Namaste, Rohan</h2>
              <p className="text-xs text-slate-500 mt-0.5">Welcome back to your secure banking</p>
            </div>
            
            {/* User Profile Avatar with green glowing online/shield badge */}
            <div className="relative w-12 h-12 rounded-full border-2 border-slate-200 overflow-hidden cursor-pointer bg-slate-100" onClick={() => handleAction('SecurityCenterActivity', 'Security Center')}>
              <img 
                src="https://lh3.googleusercontent.com/aida-public/AB6AXuC2sKMfgG0BS7c-LJP-8cxBenmee6d8uNcUY6IVyf45YNRzEKe5cHhUpzC4JcmFTy7qE02sTXeIaPNLUChCDXAZIrhHutk28Yj_HZ3V_0vGjOTbJte7wPxKZWY35hN8-c5SiJuS-TT6I8yMDYQmlHgfQlG9UjBE82xiVyQfHncR9T8N6xZKLGBVj9jdJ6CAbMjRDneaCSrPG0Se4HT3Fmyn7AnXY6cZCsqO3Osa7MW7PntRy4ms9-BER8hW3zC8klKqDV3EvhosPUM" 
                alt="Rohan Profile" 
                className="w-full h-full object-cover"
                referrerPolicy="no-referrer"
              />
              <span className="absolute bottom-0 right-0 w-3.5 h-3.5 bg-white border border-slate-200 rounded-full flex items-center justify-center">
                <Shield className="w-2.5 h-2.5 text-emerald-500 fill-emerald-500" />
              </span>
            </div>
          </section>

          {/* Primary Account Debit/Savings Card */}
          <section>
            <div className="relative overflow-hidden bg-gradient-to-br from-[#176fc1] to-[#0c4075] rounded-2xl p-5 shadow-lg border border-slate-200 text-left">
              
              {/* Futuristic vector glows */}
              <div className="absolute -top-10 -right-10 w-32 h-32 bg-white/5 rounded-full blur-2xl" />
              <div className="absolute -bottom-10 -left-10 w-24 h-24 bg-black/20 rounded-full blur-xl" />
              
              <div className="relative z-10 space-y-6">
                <div className="flex justify-between items-start">
                  <div>
                    <p className="text-[10px] font-bold tracking-widest text-[#ebf1ff]/80 uppercase">Primary Account</p>
                    <p className="text-xs text-[#ebf1ff] mt-0.5">{primaryAccount.type} • {primaryAccount.accountNo}</p>
                  </div>
                  <div className="bg-white/10 px-2 py-1 rounded-md border border-white/10 flex items-center space-x-1">
                    <span className="text-[10px] text-white font-semibold">TFLite Secure</span>
                    <Sparkles className="w-3 h-3 text-yellow-300 fill-yellow-300" />
                  </div>
                </div>

                <div>
                  <p className="text-[10px] text-[#ebf1ff]/80 font-medium">Available Balance</p>
                  <div className="flex items-baseline space-x-1.5 mt-0.5">
                    <span className="text-xl font-bold text-white">{primaryAccount.currency}</span>
                    <h3 className="text-2xl font-bold tracking-tight text-white font-sans">
                      {hideBalance ? '••••••' : primaryAccount.balance.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </h3>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-1 border-t border-white/15">
                  <button 
                    onClick={() => setHideBalance(!hideBalance)}
                    className="bg-white/15 hover:bg-white/25 px-4 py-1.5 rounded-full text-xs font-semibold flex items-center space-x-1.5 transition-colors cursor-pointer text-white"
                  >
                    {hideBalance ? (
                      <>
                        <Eye className="w-3.5 h-3.5" />
                        <span>Show Balance</span>
                      </>
                    ) : (
                      <>
                        <EyeOff className="w-3.5 h-3.5" />
                        <span>Hide Balance</span>
                      </>
                    )}
                  </button>
                  <span className="text-[10px] italic text-white/70">Last updated: Just now</span>
                </div>
              </div>
            </div>
          </section>

          {/* Quick Actions Horizontal Scrolling Grid */}
          <section>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 pl-1 text-left">Quick Actions</h3>
            <div className="flex gap-4 overflow-x-auto no-scrollbar pb-1">
              
              {/* Transfer Action button */}
              <button 
                onClick={() => handleAction('TransferActivity', 'Send Money')}
                className="flex-shrink-0 flex flex-col items-center gap-2 group cursor-pointer animate-none"
              >
                <div className="w-14 h-14 rounded-2xl bg-[#00569c] hover:bg-[#004b87] text-white flex items-center justify-center shadow-md transition-transform group-active:scale-95 duration-100">
                  <Send className="w-6 h-6 rotate-[-15deg]" />
                </div>
                <span className="text-xs font-semibold text-slate-700">Transfer</span>
              </button>

              {/* Transaction History button */}
              <button 
                onClick={() => handleAction('TransactionHistoryActivity', 'Txn History')}
                className="flex-shrink-0 flex flex-col items-center gap-2 group cursor-pointer animate-none"
              >
                <div className="w-14 h-14 rounded-2xl bg-red-500 hover:bg-red-600 text-white flex items-center justify-center shadow-md transition-transform group-active:scale-95 duration-100">
                  <History className="w-6 h-6" />
                </div>
                <span className="text-xs font-semibold text-slate-700">History</span>
              </button>

              {/* Pay Bills placeholder */}
              <button 
                onClick={() => onLog('Activity', 'Pay Bills is simulated. Navigating to Transfer Activity for active flows.', 'warning')}
                className="flex-shrink-0 flex flex-col items-center gap-2 group cursor-pointer animate-none"
              >
                <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 text-[#00569c] flex items-center justify-center shadow-sm hover:bg-slate-50 transition-transform group-active:scale-95 duration-100">
                  <Receipt className="w-6 h-6" />
                </div>
                <span className="text-xs font-semibold text-slate-500">Pay Bills</span>
              </button>

              {/* Scan QR placeholder */}
              <button 
                onClick={() => onLog('Activity', 'Scan QR Code is simulated. Navigating to Transfer Activity.', 'warning')}
                className="flex-shrink-0 flex flex-col items-center gap-2 group cursor-pointer animate-none"
              >
                <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 text-[#00569c] flex items-center justify-center shadow-sm hover:bg-slate-50 transition-transform group-active:scale-95 duration-100">
                  <QrCode className="w-6 h-6" />
                </div>
                <span className="text-xs font-semibold text-slate-500">Scan QR</span>
              </button>

              {/* Credit Cards button */}
              <button 
                onClick={() => onLog('Activity', 'Cards panel clicked.', 'info')}
                className="flex-shrink-0 flex flex-col items-center gap-2 group cursor-pointer animate-none"
              >
                <div className="w-14 h-14 rounded-2xl bg-white border border-slate-200 text-[#00569c] flex items-center justify-center shadow-sm hover:bg-slate-50 transition-transform group-active:scale-95 duration-100">
                  <CreditCard className="w-6 h-6" />
                </div>
                <span className="text-xs font-semibold text-slate-500">Cards</span>
              </button>

            </div>
          </section>

          {/* Quick Security Status Telemetry Overlay */}
          <section 
            onClick={() => handleAction('SecurityCenterActivity', 'SecurityCenter')}
            className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center justify-between cursor-pointer hover:border-[#00569c]/40 transition-colors shadow-sm"
          >
            <div className="flex items-center space-x-3 text-left">
              <div className="p-2.5 rounded-xl bg-emerald-50 text-emerald-600">
                <Shield className="w-5 h-5 fill-emerald-50" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-slate-800">CogniGuard Security Active</h4>
                <p className="text-[10px] text-emerald-600 font-semibold mt-0.5">Status: Fully Protected</p>
              </div>
            </div>
            <ChevronRight className="w-5 h-5 text-slate-400" />
          </section>

          {/* Recent Transactions List */}
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400 pl-1 text-left">Recent Transactions</h3>
              <button 
                onClick={() => handleAction('TransactionHistoryActivity', 'View All Transactions')}
                className="text-xs font-semibold text-[#00569c] hover:underline cursor-pointer"
              >
                View All
              </button>
            </div>

            <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden divide-y divide-slate-100 shadow-sm">
              {MOCK_TRANSACTIONS.map((txn) => (
                <div 
                  key={txn.id}
                  className="flex items-center justify-between p-3.5 hover:bg-slate-50 active:bg-slate-100/85 transition-colors cursor-pointer"
                >
                  <div className="flex items-center space-x-3 text-left">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      txn.type === 'credit' 
                        ? 'bg-emerald-50 text-emerald-600' 
                        : 'bg-red-50 text-red-500'
                    }`}>
                      {txn.type === 'credit' ? <ArrowDownLeft className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
                    </div>
                    <div>
                      <p className="text-xs font-bold text-slate-800">{txn.beneficiary}</p>
                      <p className="text-[10px] text-slate-400 mt-0.5">{txn.paymentMethod} • {txn.timestamp}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <p className={`text-xs font-bold font-mono ${
                      txn.type === 'credit' ? 'text-[#00569c]' : 'text-red-500'
                    }`}>
                      {txn.type === 'credit' ? '+' : '-'}₹{txn.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </p>
                    <span className="inline-flex items-center text-[9px] text-emerald-600 font-bold space-x-0.5 mt-0.5">
                      <CheckCircle2 className="w-3 h-3 fill-emerald-50" />
                      <span>Success</span>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>

      {/* Floating security action button */}
      <div className="absolute bottom-20 right-5 z-30">
        <button 
          onClick={() => handleAction('TransferActivity', 'Quick Transfer')}
          className="w-12 h-12 bg-[#00569c] hover:bg-[#004b87] text-white rounded-full shadow-lg flex items-center justify-center active:scale-90 transition-transform duration-100 cursor-pointer"
        >
          <Send className="w-5 h-5 rotate-[-15deg] pl-0.5" />
        </button>
      </div>

    </div>
  );
}
