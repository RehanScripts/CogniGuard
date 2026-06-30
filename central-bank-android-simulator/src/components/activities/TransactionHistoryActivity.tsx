import React, { useState } from 'react';
import { ArrowLeft, Search, Plus, CheckCircle2, UserCheck, ArrowUpRight, ArrowDownLeft } from 'lucide-react';
import { MOCK_TRANSACTIONS, MOCK_BENEFICIARIES } from '../../data/mockData';

interface TransactionHistoryActivityProps {
  onBack: () => void;
  onLog: (tag: 'CogniGuardClient' | 'TFLiteModel' | 'Activity' | 'NetworkGateway', message: string, level: 'info' | 'warning' | 'error' | 'success') => void;
}

export default function TransactionHistoryActivity({ onBack, onLog }: TransactionHistoryActivityProps) {
  const [filterQuery, setFilterQuery] = useState('');

  const filteredTransactions = MOCK_TRANSACTIONS.filter(t => 
    t.beneficiary.toLowerCase().includes(filterQuery.toLowerCase()) ||
    t.paymentMethod.toLowerCase().includes(filterQuery.toLowerCase())
  );

  return (
    <div id="transaction-history-activity" className="min-h-full flex flex-col bg-[#f8f9fa] text-slate-800 select-none">
      
      {/* Top App Bar */}
      <header className="flex items-center space-x-3 px-4 h-12 border-b border-slate-200/80 sticky top-0 bg-white/90 backdrop-blur-md z-10 shadow-sm">
        <button 
          onClick={onBack} 
          className="p-1.5 rounded-full hover:bg-slate-100 text-[#00569c] cursor-pointer"
        >
          <ArrowLeft className="w-5 h-5" />
        </button>
        <h1 className="text-sm font-bold font-sans text-slate-800 font-sans">Transaction History</h1>
      </header>

      {/* Main Container */}
      <div className="flex-1 overflow-y-auto no-scrollbar p-4 space-y-5 pb-20">
        
        {/* Horizontal Beneficiary Directory Panel - requested addition */}
        <section className="space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-1">Saved Beneficiaries</h3>
            <span className="text-[10px] text-[#00569c] font-semibold flex items-center space-x-1">
              <UserCheck className="w-3.5 h-3.5" />
              <span>Verified ({MOCK_BENEFICIARIES.length})</span>
            </span>
          </div>

          <div className="flex gap-4 overflow-x-auto no-scrollbar py-1">
            {MOCK_BENEFICIARIES.map((beneficiary) => (
              <div 
                key={beneficiary.id} 
                onClick={() => onLog('Activity', `Viewing details for beneficiary: ${beneficiary.name}`, 'info')}
                className="flex flex-col items-center gap-1.5 min-w-[56px] cursor-pointer"
              >
                <div className="w-11 h-11 rounded-full border border-slate-200 p-0.5 bg-white">
                  <img 
                    src={beneficiary.avatar} 
                    alt={beneficiary.name} 
                    className="w-full h-full object-cover rounded-full"
                    referrerPolicy="no-referrer"
                  />
                </div>
                <span className="text-[9px] font-semibold text-slate-500 truncate max-w-[52px]">
                  {beneficiary.name.split(' ')[0]}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Search filter input */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4.5 h-4.5 text-slate-450" />
          <input 
            type="text"
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
            placeholder="Search transactions..."
            className="w-full h-11 pl-10 pr-4 bg-white border border-slate-300 rounded-xl text-xs text-slate-800 outline-none placeholder:text-slate-400 focus:border-[#00569c] focus:ring-1 focus:ring-[#00569c] transition-all shadow-sm"
          />
        </div>

        {/* Filtered Transactions List */}
        <section className="space-y-3">
          <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-400 pl-1 text-left">All Activity</h3>
          
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden divide-y divide-slate-100 shadow-sm">
            {filteredTransactions.length > 0 ? (
              filteredTransactions.map((txn) => (
                <div 
                  key={txn.id}
                  className="flex items-center justify-between p-3.5 hover:bg-slate-50 active:bg-slate-100/85 transition-colors cursor-pointer"
                >
                  <div className="flex items-center space-x-3">
                    <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
                      txn.type === 'credit' 
                        ? 'bg-emerald-50 text-emerald-600' 
                        : 'bg-red-50 text-red-500'
                    }`}>
                      {txn.type === 'credit' ? <ArrowDownLeft className="w-5 h-5" /> : <ArrowUpRight className="w-5 h-5" />}
                    </div>
                    <div className="text-left">
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
              ))
            ) : (
              <div className="p-8 text-center text-xs text-slate-405">
                No transactions matching search filter
              </div>
            )}
          </div>
        </section>

      </div>
    </div>
  );
}
