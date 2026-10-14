import React from "react";
import { orchestrator } from "../services/botStore";
import { X, BarChart3, Download, Award, TrendingUp } from "lucide-react";

interface SpinAnalyticsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SpinAnalyticsModal: React.FC<SpinAnalyticsModalProps> = ({ isOpen, onClose }) => {
  if (!isOpen) return null;

  const brackets = orchestrator.strategy.windowBracketStats;
  const bestBracket = orchestrator.strategy.getBestProfitWindowBracket();
  const records = orchestrator.strategy.spinRecords;

  const handleDownloadCsv = () => {
    let csv = "spin_id,timestamp_iso,interval_seconds,window_bracket,phase_offset_ms,outcome,gross_payout_pat,net_delta_pat,wallet_after_pat,jackpot_pool_pat\n";
    for (const r of records) {
      csv += `${r.spin_id},"${r.timestamp_iso}",${r.interval_seconds},"${r.window_bracket}",${r.phase_offset_ms},${r.outcome},${r.gross_payout_pat},${r.net_delta_pat},${r.wallet_after_pat},${r.jackpot_pool_pat}\n`;
    }
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "spin_timing_records.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono">
      <div className="bg-[#0B1120] border border-[#FBBF24] rounded-lg max-w-4xl w-full p-5 shadow-2xl space-y-4 text-xs text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-5 h-5 text-amber-400" />
            <div>
              <h2 className="text-base font-bold text-white">Spin Timing Windows & Profit Brackets</h2>
              <p className="text-[11px] text-slate-400">
                data/spin_timing_records.csv • 30-Second Timing Brackets & Server Phase Calibration
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 4 Bracket Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {Object.entries(brackets).map(([bracket, st]) => {
            const isBest = bracket === bestBracket;
            const winRate = st.spins > 0 ? ((st.wins / st.spins) * 100).toFixed(1) : "0.0";
            return (
              <div
                key={bracket}
                className={`p-3 rounded border ${
                  isBest
                    ? "bg-amber-950/40 border-amber-400 shadow-md shadow-amber-500/10"
                    : "bg-[#050811] border-slate-800"
                } space-y-1`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-200 text-[11px]">{bracket.split(" ")[0]}</span>
                  {isBest && (
                    <span className="flex items-center gap-0.5 text-[9px] font-bold text-amber-400 bg-amber-950 px-1 py-0.5 rounded border border-amber-600/50">
                      <Award className="w-2.5 h-2.5" />
                      BEST EV
                    </span>
                  )}
                </div>
                <div className="text-[10px] text-slate-400">{bracket.split(" ")[1] || ""}</div>
                <div className="pt-1.5 space-y-0.5 text-[11px]">
                  <div>Spins: <strong className="text-slate-100">{st.spins}</strong></div>
                  <div>Win Rate: <strong className="text-emerald-400">{winRate}%</strong></div>
                  <div>Jackpots: <strong className="text-yellow-400">{st.jackpots}</strong></div>
                  <div>
                    Net P/L:{" "}
                    <strong className={st.net_pat >= 0 ? "text-emerald-400" : "text-rose-400"}>
                      {st.net_pat >= 0 ? "+" : ""}{st.net_pat.toLocaleString()} PAT
                    </strong>
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Recent Spins Table */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-300 flex items-center gap-1">
              <TrendingUp className="w-4 h-4 text-emerald-400" />
              <span>Recent Spin Records ({records.length} total)</span>
            </span>
            <button
              onClick={handleDownloadCsv}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-[#F59E0B] hover:bg-[#FBBF24] text-[#090D16] font-bold transition-all cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export CSV</span>
            </button>
          </div>

          <div className="border border-slate-800 rounded bg-[#050811] max-h-48 overflow-y-auto">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead className="bg-slate-900 sticky top-0 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-1.5">ID</th>
                  <th className="p-1.5">Interval</th>
                  <th className="p-1.5">Window Bracket</th>
                  <th className="p-1.5">Offset</th>
                  <th className="p-1.5">Outcome</th>
                  <th className="p-1.5">Gross</th>
                  <th className="p-1.5">Net Delta</th>
                  <th className="p-1.5">Wallet</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {records.slice(0, 15).map((r) => (
                  <tr key={r.spin_id} className="hover:bg-slate-800/40">
                    <td className="p-1.5 text-slate-400">#{r.spin_id}</td>
                    <td className="p-1.5 font-bold text-sky-300">{r.interval_seconds.toFixed(2)}s</td>
                    <td className="p-1.5 text-slate-300">{r.window_bracket.split(" ")[0]}</td>
                    <td className="p-1.5 text-slate-400">+{r.phase_offset_ms}ms</td>
                    <td className="p-1.5">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                          r.outcome === "JACKPOT"
                            ? "bg-yellow-950 text-yellow-300 border border-yellow-500"
                            : r.outcome === "WIN"
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-600/50"
                            : "bg-red-950/60 text-rose-300 border border-rose-800/50"
                        }`}
                      >
                        {r.outcome}
                      </span>
                    </td>
                    <td className="p-1.5 text-slate-200">+{r.gross_payout_pat.toLocaleString()}</td>
                    <td className={`p-1.5 font-bold ${r.net_delta_pat >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {r.net_delta_pat >= 0 ? "+" : ""}{r.net_delta_pat.toLocaleString()}
                    </td>
                    <td className="p-1.5 text-amber-300">{r.wallet_after_pat.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
          <span className="text-[11px] text-slate-400">
            Optimal timing offset: <strong className="text-amber-400">+{orchestrator.strategy.optimalSpinOffsetMs}ms</strong>
          </span>
          <button
            onClick={onClose}
            className="px-4 py-1 rounded bg-slate-800 hover:bg-slate-700 text-white font-bold cursor-pointer"
          >
            Close Analytics
          </button>
        </div>
      </div>
    </div>
  );
};
