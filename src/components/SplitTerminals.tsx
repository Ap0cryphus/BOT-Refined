import React, { useState, useEffect, useRef } from "react";
import { orchestrator } from "../services/botStore";
import { TerminalLine } from "../types";
import { Trash2, Copy, ArrowDownCircle, Search } from "lucide-react";

interface TerminalViewProps {
  title: string;
  lines: TerminalLine[];
  headerBg: string;
  headerFg: string;
  borderColor: string;
  accentBg: string;
  textColor: string;
  heightClass: string;
  onClear: () => void;
}

const TerminalView: React.FC<TerminalViewProps> = ({
  title,
  lines,
  headerBg,
  headerFg,
  borderColor,
  textColor,
  heightClass,
  onClear,
}) => {
  const [filter, setFilter] = useState("");
  const [autoScroll, setAutoScroll] = useState(true);
  const bodyRef = useRef<HTMLDivElement>(null);

  const filteredLines = filter
    ? lines.filter((l) => l.text.toLowerCase().includes(filter.toLowerCase()))
    : lines;

  useEffect(() => {
    if (autoScroll && bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  const handleCopy = () => {
    const text = filteredLines.map((l) => `[${l.timestamp}] ${l.text}`).join("\n");
    navigator.clipboard.writeText(text);
  };

  return (
    <div
      className={`flex flex-col bg-[#050811] rounded border ${borderColor} shadow-xl overflow-hidden font-mono text-xs`}
    >
      {/* Terminal Header */}
      <div className={`${headerBg} px-3 py-1 flex items-center justify-between border-b border-slate-800`}>
        <div className="flex items-center gap-2">
          <span className={`font-bold ${headerFg} tracking-tight`}>{title}</span>
          <span className="text-[10px] text-slate-400 font-normal">
            ({filteredLines.length} lines)
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Filter */}
          <div className="relative flex items-center">
            <Search className="w-3 h-3 text-slate-400 absolute left-1.5 pointer-events-none" />
            <input
              type="text"
              placeholder="Filter..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-black/60 border border-slate-700/60 rounded pl-5 pr-1.5 py-0.5 text-[11px] text-slate-200 placeholder-slate-500 w-24 focus:w-36 transition-all focus:outline-none"
            />
          </div>

          {/* Auto-scroll toggle */}
          <button
            onClick={() => setAutoScroll(!autoScroll)}
            title={autoScroll ? "Auto-scroll ON" : "Auto-scroll OFF"}
            className={`p-1 rounded cursor-pointer transition-all ${
              autoScroll ? "text-emerald-400 bg-emerald-950/60" : "text-slate-500 hover:text-slate-300"
            }`}
          >
            <ArrowDownCircle className="w-3.5 h-3.5" />
          </button>

          {/* Copy */}
          <button
            onClick={handleCopy}
            title="Copy terminal contents"
            className="p-1 rounded text-slate-400 hover:text-slate-200 cursor-pointer transition-all"
          >
            <Copy className="w-3.5 h-3.5" />
          </button>

          {/* Clear */}
          <button
            onClick={onClear}
            title="Clear terminal"
            className="p-1 rounded text-slate-400 hover:text-red-400 cursor-pointer transition-all"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Body with translucent overlay */}
      <div
        ref={bodyRef}
        className={`${heightClass} overflow-y-auto p-2 space-y-1 bg-[#050811]/95 ${textColor} select-text leading-relaxed font-mono text-[11.5px]`}
      >
        {filteredLines.length === 0 ? (
          <div className="text-slate-500 italic py-2">No log entries matching criteria...</div>
        ) : (
          filteredLines.map((l) => {
            const isHighlight =
              l.text.includes("WIN") ||
              l.text.includes("JACKPOT") ||
              l.text.includes("LOCKED") ||
              l.text.includes("SPEAKER_ON_MIC");
            const isError = l.text.includes("ERR") || l.text.includes("LOSS") || l.text.includes("STOP");

            return (
              <div
                key={l.id}
                className={`py-0.5 px-1.5 rounded transition-colors break-words ${
                  isHighlight
                    ? "bg-emerald-950/20 text-emerald-300 font-medium"
                    : isError
                    ? "bg-red-950/20 text-rose-300"
                    : "hover:bg-slate-900/50"
                }`}
              >
                <span className="text-slate-500 select-none mr-2">[{l.timestamp}]</span>
                <span>{l.text}</span>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export const SplitTerminals: React.FC = () => {
  const [t1, setT1] = useState<TerminalLine[]>(orchestrator.terminal1);
  const [t2, setT2] = useState<TerminalLine[]>(orchestrator.terminal2);
  const [t3, setT3] = useState<TerminalLine[]>(orchestrator.terminal3);

  useEffect(() => {
    return orchestrator.subscribe(() => {
      setT1([...orchestrator.terminal1]);
      setT2([...orchestrator.terminal2]);
      setT3([...orchestrator.terminal3]);
    });
  }, []);

  return (
    <div className="flex flex-col gap-2.5">
      {/* TERMINAL 1 (TOP): INCOMING ROOM FEED */}
      <TerminalView
        title="📥 TERMINAL 1: INCOMING ROOM FEED (CHAT • SPEAKER_ON_MIC • PRESENCE • USER DB)"
        lines={t1}
        headerBg="bg-[#06281E]"
        headerFg="text-[#34D399]"
        borderColor="border-[#10B981]/50"
        accentBg="bg-[#070B14]"
        textColor="text-[#A7F3D0]"
        heightClass="h-44 md:h-52"
        onClear={() => {
          orchestrator.terminal1 = [];
          setT1([]);
        }}
      />

      {/* TERMINAL 2 (MIDDLE): BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER */}
      <TerminalView
        title="📤 TERMINAL 2: BOT ACTIONS, TRIGGERS & ALL-SPINS ANALYZER (data/spin_timing_records.csv)"
        lines={t2}
        headerBg="bg-[#280910]"
        headerFg="text-[#FBBF24]"
        borderColor="border-[#EF4444]/50"
        accentBg="bg-[#0A0710]"
        textColor="text-[#FDE68A]"
        heightClass="h-44 md:h-52"
        onClear={() => {
          orchestrator.terminal2 = [];
          setT2([]);
        }}
      />

      {/* TERMINAL 3 (BOTTOM): LIVE TRANSCRIPTION + VOICE CLONE PROGRESS */}
      <TerminalView
        title="🎙️ TERMINAL 3: LIVE TRANSCRIPTION (real-time [MIC] <User>: '<text>') • VOICE SAMPLE / CLONE PROGRESS"
        lines={t3}
        headerBg="bg-[#0A1E2E]"
        headerFg="text-[#38BDF8]"
        borderColor="border-[#38BDF8]/50"
        accentBg="bg-[#060E1A]"
        textColor="text-[#7DD3FC]"
        heightClass="h-32 md:h-36"
        onClear={() => {
          orchestrator.terminal3 = [];
          setT3([]);
        }}
      />
    </div>
  );
};
