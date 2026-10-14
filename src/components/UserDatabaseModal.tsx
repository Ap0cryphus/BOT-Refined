import React, { useState } from "react";
import { orchestrator } from "../services/botStore";
import { UserProfile } from "../types";
import { X, Database, Search, UserCheck, ShieldAlert, FileText, Mic } from "lucide-react";

interface UserDatabaseModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const UserDatabaseModal: React.FC<UserDatabaseModalProps> = ({ isOpen, onClose }) => {
  const [searchTerm, setSearchTerm] = useState("");
  const [selectedUser, setSelectedUser] = useState<UserProfile | null>(null);

  if (!isOpen) return null;

  const userList = Array.from(orchestrator.users.values());
  const filteredUsers = searchTerm
    ? userList.filter((u) => u.username.toLowerCase().includes(searchTerm.toLowerCase()))
    : userList;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono">
      <div className="bg-[#0B1120] border border-[#38BDF8] rounded-lg max-w-4xl w-full p-5 shadow-2xl space-y-4 text-xs text-slate-200">
        <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-sky-400" />
            <div>
              <h2 className="text-base font-bold text-white">SQLite 5.1/5.2 Database Inspector</h2>
              <p className="text-[11px] text-slate-400">
                data/camfrog_bot.db • users, chat_history, user_activity, message_analysis, mic_grabs
              </p>
            </div>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Search */}
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search users by name, gender, top noun..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#050811] border border-slate-800 rounded pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-sky-500"
          />
        </div>

        {/* Main Grid: User table + Profile card */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 max-h-[50vh] overflow-hidden">
          {/* User List Table */}
          <div className="border border-slate-800 rounded bg-[#050811] overflow-y-auto max-h-[50vh]">
            <table className="w-full text-left border-collapse text-[11px]">
              <thead className="bg-slate-900 sticky top-0 text-slate-400 border-b border-slate-800">
                <tr>
                  <th className="p-2">User</th>
                  <th className="p-2">Gender</th>
                  <th className="p-2">Msgs</th>
                  <th className="p-2">Mic Grabs</th>
                  <th className="p-2">Top Noun</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredUsers.map((u) => {
                  const isSuppressed = orchestrator.suppressedUsers.has(u.username.toLowerCase());
                  return (
                    <tr
                      key={u.username}
                      onClick={() => setSelectedUser(u)}
                      className={`hover:bg-slate-800/50 cursor-pointer transition-colors ${
                        selectedUser?.username === u.username ? "bg-sky-950/50" : ""
                      }`}
                    >
                      <td className="p-2 font-bold text-slate-100 flex items-center gap-1">
                        {isSuppressed && <ShieldAlert className="w-3 h-3 text-red-400" />}
                        <span>{u.username}</span>
                      </td>
                      <td className="p-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] ${
                            u.gender.includes("pink")
                              ? "bg-pink-950/60 text-pink-300 border border-pink-700/40"
                              : u.gender.includes("blue")
                              ? "bg-blue-950/60 text-blue-300 border border-blue-700/40"
                              : "text-slate-400"
                          }`}
                        >
                          {u.gender}
                        </span>
                      </td>
                      <td className="p-2 text-slate-300">{u.message_count}</td>
                      <td className="p-2 text-slate-300">{u.mic_grab_count}</td>
                      <td className="p-2 text-amber-300 font-medium">{u.top_noun}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* User Profile Detail */}
          <div className="border border-slate-800 rounded bg-[#050811] p-3 overflow-y-auto max-h-[50vh] space-y-3">
            {selectedUser ? (
              <>
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <div>
                    <h3 className="text-sm font-bold text-white flex items-center gap-1.5">
                      <UserCheck className="w-4 h-4 text-emerald-400" />
                      <span>{selectedUser.username}</span>
                    </h3>
                    <div className="text-[10px] text-slate-400">
                      Status: {selectedUser.status_category} • Seen since {selectedUser.first_seen}
                    </div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-slate-800 text-slate-200">
                    {selectedUser.gender}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px]">
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-slate-400 text-[10px]">Text Tone:</div>
                    <div className="text-emerald-400 font-bold">{selectedUser.text_tone}</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-slate-400 text-[10px]">Speech Cadence:</div>
                    <div className="text-sky-400 font-bold">{selectedUser.speech_patterns}</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-slate-400 text-[10px]">Top Noun Obsession:</div>
                    <div className="text-amber-400 font-bold">"{selectedUser.top_noun}"</div>
                  </div>
                  <div className="bg-slate-900 p-2 rounded border border-slate-800">
                    <div className="text-slate-400 text-[10px]">Mic Time (24h):</div>
                    <div className="text-purple-400 font-bold">
                      {selectedUser.mic_grab_count} grabs ({selectedUser.total_mic_seconds}s)
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-slate-400 text-[10px] font-bold flex items-center gap-1">
                    <FileText className="w-3 h-3 text-slate-400" />
                    <span>Synthesized Narrative Biography:</span>
                  </div>
                  <p className="text-[11px] text-slate-200 bg-slate-900 p-2 rounded border border-slate-800 leading-relaxed">
                    {selectedUser.biography || "User history recorded in SQLite DB."}
                  </p>
                </div>

                {selectedUser.mic_transcripts.length > 0 && (
                  <div className="space-y-1">
                    <div className="text-slate-400 text-[10px] font-bold flex items-center gap-1">
                      <Mic className="w-3 h-3 text-sky-400" />
                      <span>Recent Spoken Mic Transcripts:</span>
                    </div>
                    <div className="space-y-1">
                      {selectedUser.mic_transcripts.map((t, idx) => (
                        <div key={idx} className="text-[11px] text-sky-200 bg-sky-950/30 p-1.5 rounded border border-sky-800/40 italic">
                          "{t}"
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-center justify-center h-full text-slate-500 italic">
                Select a user from the table to view their full SQLite psychometric profile...
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
          <div className="text-[11px] text-slate-400">
            Suppressed Users Vault: {orchestrator.suppressedUsers.size} users
          </div>
          <button
            onClick={onClose}
            className="px-4 py-1 rounded bg-slate-800 hover:bg-slate-700 text-white font-bold cursor-pointer"
          >
            Close Inspector
          </button>
        </div>
      </div>
    </div>
  );
};
