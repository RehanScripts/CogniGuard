import React, { useState } from 'react';
import { FileCode, Layers, Database, Code, Check } from 'lucide-react';
import { KOTLIN_CODE_SNIPPETS } from '../data/mockData';

interface CodeViewerProps {
  activeTab: string;
}

export default function CodeViewer({ activeTab }: CodeViewerProps) {
  const [selectedFile, setSelectedFile] = useState<string>(activeTab);
  const [copied, setCopied] = useState(false);

  // Auto-sync selected tab with the phone's current active activity
  React.useEffect(() => {
    if (KOTLIN_CODE_SNIPPETS[activeTab as keyof typeof KOTLIN_CODE_SNIPPETS]) {
      setSelectedFile(activeTab);
    }
  }, [activeTab]);

  const files = [
    { id: 'LoginActivity', name: 'LoginActivity.kt', icon: FileCode },
    { id: 'DashboardActivity', name: 'DashboardActivity.kt', icon: FileCode },
    { id: 'TransferActivity', name: 'TransferActivity.kt', icon: FileCode },
    { id: 'TransferSuccessActivity', name: 'TransferSuccessActivity.kt', icon: FileCode },
    { id: 'SecurityCenterActivity', name: 'SecurityCenterActivity.kt', icon: FileCode },
    { id: 'TransactionHistoryActivity', name: 'TransactionHistoryActivity.kt', icon: FileCode },
    { id: 'CogniGuardClient', name: 'CogniGuardClient.kt', icon: Layers },
  ];

  const currentCode = KOTLIN_CODE_SNIPPETS[selectedFile as keyof typeof KOTLIN_CODE_SNIPPETS] || '';

  const handleCopy = () => {
    navigator.clipboard.writeText(currentCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  // Lightweight Kotlin syntax highlighter using regex replacements
  const highlightCode = (code: string) => {
    if (!code) return '';
    
    // Escape HTML special chars
    let escaped = code
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Comments (must do early)
    escaped = escaped.replace(/(\/\/.*)/g, '<span class="text-slate-500 italic">$1</span>');

    // Strings
    escaped = escaped.replace(/("[^"]*")/g, '<span class="text-emerald-400">$1</span>');

    // Kotlin Keywords
    const keywords = [
      'package', 'import', 'class', 'fun', 'val', 'var', 'private', 'override',
      'when', 'if', 'else', 'return', 'null', 'this', 'super', 'interface', 'apply'
    ];
    const kwRegex = new RegExp(`\\b(${keywords.join('|')})\\b`, 'g');
    escaped = escaped.replace(kwRegex, '<span class="text-pink-400">$1</span>');

    // Types
    const types = ['Intent', 'Bundle', 'AppCompatActivity', 'CogniGuardClient', 'Behavior', 'LoginResult', 'String', 'Double', 'Float', 'Long', 'Date', 'SimpleDateFormat', 'TxnControls', 'Context', 'SecuritySettingsResponse', 'PaymentScoreResult'];
    const typeRegex = new RegExp(`\\b(${types.join('|')})\\b`, 'g');
    escaped = escaped.replace(typeRegex, '<span class="text-cyan-400 font-semibold">$1</span>');

    return escaped;
  };

  return (
    <div className="bg-white border border-slate-200 rounded-2xl flex flex-col h-[520px] overflow-hidden shadow-sm">
      
      {/* Tab bar header */}
      <div className="bg-slate-50 border-b border-slate-200/80 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center space-x-2 text-xs font-bold text-slate-800">
          <Code className="w-4 h-4 text-[#00569c]" />
          <span className="font-mono tracking-wider">Android Source Code Explorer</span>
        </div>
        
        {/* Copy button */}
        <button 
          onClick={handleCopy}
          className="text-[10px] bg-white hover:bg-slate-50 border border-slate-200 px-2.5 py-1 rounded text-slate-500 hover:text-slate-800 font-mono transition-colors flex items-center space-x-1 cursor-pointer shadow-xs"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-emerald-600">Copied!</span>
            </>
          ) : (
            <span>Copy Code</span>
          )}
        </button>
      </div>

      {/* Grid container for file lists & code editor */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Left column sidebar for filenames */}
        <div className="w-1/3 border-r border-slate-200/80 bg-slate-50/50 flex flex-col overflow-y-auto no-scrollbar divide-y divide-slate-100">
          <div className="p-2 text-[9px] font-bold text-slate-400 uppercase tracking-wider pl-3">
            Source Tree
          </div>
          {files.map((file) => {
            const Icon = file.icon;
            const isSelected = selectedFile === file.id;
            return (
              <button
                key={file.id}
                onClick={() => setSelectedFile(file.id)}
                className={`w-full flex items-center space-x-2 px-3 py-2.5 text-left transition-colors cursor-pointer ${
                  isSelected 
                    ? 'bg-white text-[#00569c] font-bold border-l-2 border-l-[#00569c]' 
                    : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800'
                }`}
              >
                <Icon className={`w-3.5 h-3.5 shrink-0 ${isSelected ? 'text-[#00569c]' : 'text-slate-450'}`} />
                <span className="font-mono text-[10px] truncate">{file.name}</span>
              </button>
            );
          })}
        </div>

        {/* Right column syntax highlighted editor */}
        <div className="flex-1 bg-[#0f111a] overflow-auto p-4 font-mono text-[10px] leading-relaxed relative no-scrollbar">
          
          {/* Subtle watermark */}
          <div className="absolute right-4 bottom-4 text-slate-700 text-[8px] font-bold uppercase tracking-widest opacity-25 pointer-events-none">
            CogniGuard Android SDK
          </div>

          {/* Highlights */}
          <pre className="text-indigo-200 whitespace-pre-wrap select-text selection:bg-[#00569c]/30">
            <code dangerouslySetInnerHTML={{ __html: highlightCode(currentCode) }} />
          </pre>
        </div>

      </div>

    </div>
  );
}
