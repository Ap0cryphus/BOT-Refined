import React from "react";
import { orchestrator } from "../services/botStore";

export const TriggerDecks: React.FC = () => {
  const handleCommand = (cmd: string) => {
    orchestrator.sendManualChat(cmd);
  };

  const kaekaeTriggers: [string, string][] = [
    ["!chat", "!chat"],
    ["!chatoff", "!chatoff"],
    ["!shutup", "!shutup"],
    ["!transcribe", "!transcribe"],
    ["!transcribed", "!transcribed"],
    ["!suppress", "!suppress"],
    ["!unsuppress", "!unsuppress"],
    ["!grabs 24h", "!grabs 24h"],
    ["!diss", "!diss the room"],
    ["!idk", "!idk what is the jackpot"],
    ["!happy", "!happy"],
    ["!sad", "!sad"],
    ["!mad", "!mad"],
    ["!triggers", "!triggers"],
    ["Next Page (-)", "-"],
    ["!say Hello", "!say KaeKae Toad live on the microphone"],
    ["!admins", "!admins"],
  ];

  const heistTriggers: [string, string][] = [
    ["!sheet", "!sheet"],
    ["!heist store", "!heist store"],
    ["!heist casino", "!heist casino"],
    ["!heist convoy", "!heist convoy"],
    ["!heist bank", "!heist bank"],
    ["!join", "!join"],
    ["!bail (+20%)", "!bail"],
    ["!defend", "!defend"],
    ["!allot INT", "!allot int"],
    ["!allot DEX", "!allot dex"],
    ["!allot CON", "!allot con"],
    ["!ring INT", "!ring int"],
    ["!reroll CHA", "!reroll cha"],
    ["!shop", "!shop"],
    ["!buy lawyer", "!buy lawyer 1"],
    ["!buy ghost", "!buy ghost 1"],
    ["!buy lockpick", "!buy lockpick 2"],
    ["!gear", "!gear"],
  ];

  const gameTriggers: [string, string][] = [
    ["!spin (5k)", "!spin"],
    ["!balance", "!balance"],
    ["!lotto quick", "!lotto quick"],
    ["!bingo start", "!bingo start"],
    ["!bingo buy 4", "!bingo buy 4"],
    ["!bingo CALL!", "!bingo"],
    ["!trivia 1000", "!trivia 1000"],
    ["!showdown", "!showdown"],
    ["!guess 5000", "!guess 5000"],
    ["!arena 5000", "!arena 5000"],
    ["!brawl", "!brawl Stonerwayne1000 2500"],
    ["!duel", "!duel Stonerwayne1000 1000"],
    ["!bj 1000", "!bet 1000"],
    ["!holdem", "!holdem start 50/100"],
  ];

  return (
    <div className="flex flex-col gap-1 bg-[#060A12] font-mono text-xs">
      {/* KaeKae Row */}
      <div className="bg-[#0B1120] border border-slate-800/80 rounded px-2.5 py-1.5 flex flex-wrap items-center gap-1.5">
        <span className="font-bold text-[#34D399] w-48 shrink-0 text-left">
          🐸 KAEKAE_TOAD TRIGGERS:
        </span>
        <div className="flex flex-wrap items-center gap-1">
          {kaekaeTriggers.map(([label, cmd]) => (
            <button
              key={label}
              onClick={() => handleCommand(cmd)}
              className="px-2 py-0.5 rounded bg-[#1E293B] hover:bg-[#334155] active:bg-[#064E3B] text-[#F8FAFC] hover:text-[#34D399] border border-slate-700/60 text-[11px] font-bold transition-all cursor-pointer shadow-sm active:scale-95"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Heist Row */}
      <div className="bg-[#0B1120] border border-slate-800/80 rounded px-2.5 py-1.5 flex flex-wrap items-center gap-1.5">
        <span className="font-bold text-[#FBBF24] w-48 shrink-0 text-left">
          🔫 !HEIST & STRONGEST CHAR:
        </span>
        <div className="flex flex-wrap items-center gap-1">
          {heistTriggers.map(([label, cmd]) => (
            <button
              key={label}
              onClick={() => handleCommand(cmd)}
              className="px-2 py-0.5 rounded bg-[#1E293B] hover:bg-[#334155] active:bg-[#78350F] text-[#F8FAFC] hover:text-[#FBBF24] border border-slate-700/60 text-[11px] font-bold transition-all cursor-pointer shadow-sm active:scale-95"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Games Row */}
      <div className="bg-[#0B1120] border border-slate-800/80 rounded px-2.5 py-1.5 flex flex-wrap items-center gap-1.5">
        <span className="font-bold text-[#38BDF8] w-48 shrink-0 text-left">
          🎰 PEPEFROG GAMES (#cat-games):
        </span>
        <div className="flex flex-wrap items-center gap-1">
          {gameTriggers.map(([label, cmd]) => (
            <button
              key={label}
              onClick={() => handleCommand(cmd)}
              className="px-2 py-0.5 rounded bg-[#1E293B] hover:bg-[#334155] active:bg-[#0C4A6E] text-[#F8FAFC] hover:text-[#38BDF8] border border-slate-700/60 text-[11px] font-bold transition-all cursor-pointer shadow-sm active:scale-95"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
