import React from "react";
import { Users, BarChart3, Sword, Database } from "lucide-react";

interface HeroBannerProps {
  onOpenUsers: () => void;
  onOpenAnalytics: () => void;
  onOpenHeist: () => void;
}

export const HeroBanner: React.FC<HeroBannerProps> = ({ onOpenUsers, onOpenAnalytics, onOpenHeist }) => {
  return (
    <div className="relative w-full h-36 md:h-44 rounded-md overflow-hidden border border-[#EF4444]/70 bg-[#090508] shadow-2xl group">
      {/* Background Hero Artwork */}
      <img
        src="/pepe_gui_banner.jpg"
        alt="KaeKae Toad & PepeFrog Banner"
        className="w-full h-full object-cover object-center opacity-85 group-hover:scale-102 transition-transform duration-700"
        onError={(e) => {
          // Fallback to LOGO FOR GUI.png
          (e.target as HTMLImageElement).src = "/LOGO%20FOR%20GUI.png";
        }}
      />

      {/* Dark gradient vignette overlays for crisp terminal contrast */}
      <div className="absolute inset-0 bg-gradient-to-r from-[#060A12]/90 via-[#060A12]/40 to-[#060A12]/90" />
      <div className="absolute inset-0 bg-gradient-to-t from-[#060A12] via-transparent to-black/50" />

      {/* Top Banner Badges */}
      <div className="absolute top-2 left-3 right-3 flex items-center justify-between pointer-events-none">
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-red-600/80 text-white border border-red-400">
            CAMFROG ROOM: Players__Lounge
          </span>
          <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-600/80 text-white border border-emerald-400 flex items-center gap-1">
            <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
            DIRECTML DX12 ACCELERATED
          </span>
        </div>

        <div className="flex items-center gap-1.5 pointer-events-auto">
          <button
            onClick={onOpenUsers}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-[#1E293B]/80 hover:bg-[#334155] text-[#38BDF8] border border-[#38BDF8]/40 transition-all cursor-pointer backdrop-blur"
          >
            <Database className="w-3 h-3" />
            <span>SQLite 5.1/5.2 DB</span>
          </button>
          <button
            onClick={onOpenAnalytics}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-[#1E293B]/80 hover:bg-[#334155] text-[#FBBF24] border border-[#FBBF24]/40 transition-all cursor-pointer backdrop-blur"
          >
            <BarChart3 className="w-3 h-3" />
            <span>Spin Window Brackets</span>
          </button>
          <button
            onClick={onOpenHeist}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-[#1E293B]/80 hover:bg-[#334155] text-[#34D399] border border-[#34D399]/40 transition-all cursor-pointer backdrop-blur"
          >
            <Sword className="w-3 h-3" />
            <span>Heist Character Sheet</span>
          </button>
        </div>
      </div>

      {/* Hero Title & Subtitle */}
      <div className="absolute bottom-2 left-4 right-4 flex items-end justify-between">
        <div>
          <h1 className="text-lg md:text-xl font-extrabold tracking-wide text-transparent bg-clip-text bg-gradient-to-r from-red-400 via-amber-300 to-emerald-400 drop-shadow-md">
            KAEKAE_TOAD & PEPEFROG SUPREME COMMAND GUI
          </h1>
          <p className="text-[11px] font-mono text-slate-300">
            Precision Automation Orchestrator • publicaccess.tv Heist Optimizer • Live DirectML Neural Audio
          </p>
        </div>

        <div className="hidden md:flex items-center gap-3 text-[11px] font-mono text-slate-300 bg-black/60 px-3 py-1 rounded border border-slate-700/60 backdrop-blur">
          <span>
            Bot HWND: <strong className="text-emerald-400">0x001A03F2</strong>
          </span>
          <span>•</span>
          <span>
            Tick: <strong className="text-amber-400">20.200s</strong>
          </span>
          <span>•</span>
          <span>
            Pity Net: <strong className="text-sky-400">&gt;= 6 Losses</strong>
          </span>
        </div>
      </div>
    </div>
  );
};
