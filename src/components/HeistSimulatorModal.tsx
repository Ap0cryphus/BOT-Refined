import React, { useState } from "react";
import { orchestrator } from "../services/botStore";
import { X, Sword, Shield, DollarSign, PlusCircle, CheckCircle } from "lucide-react";

interface HeistSimulatorModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const HeistSimulatorModal: React.FC<HeistSimulatorModalProps> = ({ isOpen, onClose }) => {
  const [job, setJob] = useState("casino");
  const [accruedLoot, setAccruedLoot] = useState(42000);
  const [crewSize, setCrewSize] = useState(3);
  const [char, setChar] = useState(orchestrator.strategy.heistCharacter);

  if (!isOpen) return null;

  const evaluation = orchestrator.strategy.evaluateVaultDoorVsBail(job, accruedLoot, orchestrator.strategy.jackpotPoolPat, crewSize);

  const handleAllot = (statName: "STR" | "DEX" | "CON" | "INT" | "WIS" | "CHA") => {
    orchestrator.strategy.heistCharacter.stats[statName] += 1;
    orchestrator.strategy.updateHeistDerived();
    setChar({ ...orchestrator.strategy.heistCharacter });
    orchestrator.emitActionLog(`[HEIST ALLOT] Incremented ${statName} -> ${orchestrator.strategy.heistCharacter.stats[statName]}`);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono">
      <div className="bg-[#0B1120] border border-[#34D399] rounded-lg max-w-3xl w-full p-5 shadow-2xl space-y-4 text-xs text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
          <div className="flex items-center gap-2">
            <Sword className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="text-base font-bold text-white">Grand Theft Frogger (!heist) Sheet & Simulator</h2>
              <p className="text-[11px] text-slate-400">
                publicaccess.tv/help#cat-heists • 6 D&D Attributes, Relics, Gear & Vault Door Probability
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* 6 D&D Stats Grid */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <span className="font-bold text-slate-300">
              Character: <strong className="text-amber-400">{char.character_class}</strong> (Total Power: {char.total_stat_power})
            </span>
            <span className="text-slate-400 text-[11px]">Click [+] to test allocating stat points</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-2 text-center">
            {(Object.entries(char.stats) as [keyof typeof char.stats, number][]).map(([stat, val]) => (
              <div key={stat} className="bg-[#050811] p-2 rounded border border-slate-800 space-y-1">
                <div className="text-[10px] text-slate-400 font-bold">{stat}</div>
                <div className="text-base font-extrabold text-emerald-400">{val}</div>
                <button
                  onClick={() => handleAllot(stat)}
                  className="w-full py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-[10px] font-bold flex items-center justify-center gap-1 cursor-pointer"
                >
                  <PlusCircle className="w-3 h-3 text-emerald-400" />
                  <span>Allot</span>
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* Relics & Gear */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-[11px]">
          <div className="bg-[#050811] p-2.5 rounded border border-slate-800 space-y-1">
            <div className="font-bold text-amber-300">Equipped Relics:</div>
            <div className="flex flex-wrap gap-1">
              {char.relics.map((r) => (
                <span key={r} className="px-2 py-0.5 rounded bg-amber-950/60 border border-amber-600/50 text-amber-200">
                  💍 {r}
                </span>
              ))}
            </div>
          </div>

          <div className="bg-[#050811] p-2.5 rounded border border-slate-800 space-y-1">
            <div className="font-bold text-emerald-300">Tactical Gear:</div>
            <div className="flex flex-wrap gap-1">
              {char.gear.map((g) => (
                <span key={g} className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-600/50 text-emerald-200">
                  ⚖️ {g}
                </span>
              ))}
            </div>
          </div>
        </div>

        {/* Vault Door Simulator */}
        <div className="bg-[#050811] p-3 rounded border border-slate-800 space-y-2">
          <div className="font-bold text-sky-300">Vault Door Crack Odds vs !bail Decision Engine:</div>
          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="text-slate-400 text-[10px]">Job Target:</label>
              <select
                value={job}
                onChange={(e) => setJob(e.target.value)}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100"
              >
                <option value="store">Store (Round 4/4)</option>
                <option value="casino">Casino (Round 9/9)</option>
                <option value="convoy">Armored Convoy (Round 10/10)</option>
                <option value="bank">Federal Reserve Bank (Round 11/11)</option>
              </select>
            </div>
            <div>
              <label className="text-slate-400 text-[10px]">Accrued Loot (PAT):</label>
              <input
                type="number"
                value={accruedLoot}
                onChange={(e) => setAccruedLoot(Number(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100"
              />
            </div>
            <div>
              <label className="text-slate-400 text-[10px]">Crew Members:</label>
              <input
                type="number"
                value={crewSize}
                onChange={(e) => setCrewSize(Number(e.target.value))}
                className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-100"
              />
            </div>
          </div>

          <div className="p-2.5 rounded bg-slate-900 border border-slate-800 space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-bold text-slate-300">
                Recommended Action:{" "}
                <strong className={evaluation.action === "!bail" ? "text-amber-400" : "text-emerald-400"}>
                  {evaluation.action}
                </strong>
              </span>
              <span className="text-[11px] text-slate-400">
                Door Crack Odds: <strong className="text-sky-300">{(evaluation.crackProb * 100).toFixed(0)}%</strong>
              </span>
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">{evaluation.reason}</p>
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
          <div className="text-[11px] text-emerald-400">
            Recommended Upgrade: {char.recommended_upgrade_cmd}
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1 rounded bg-[#10B981] hover:bg-[#34D399] text-[#022C22] font-bold cursor-pointer"
          >
            Close Sheet
          </button>
        </div>
      </div>
    </div>
  );
};
