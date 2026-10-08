import React, { useState, useMemo } from 'react';
import {
  CamfrogBotEngine,
  ROOM_TAB_POSITIONS,
  RoomName,
  UIANode,
  cleanUsername,
  detectModeration,
  runOfflineBotTests,
  TestCaseResult,
  TRIGGER_NAMES,
  CAMFROG_WINDOW_TITLE_RE,
  POLL_INTERVAL_SECONDS,
  UIA_CACHE_SECONDS,
  MAX_CHAT_MESSAGE_LENGTH,
} from './lib/camfrogBot';
import {
  Send,
  Play,
  Terminal,
  Database,
  ShieldAlert,
  Mic,
  UserPlus,
  UserMinus,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Search,
  Lock,
  Unlock,
} from 'lucide-react';

type ActiveSection = 'monitor' | 'database' | 'uia' | 'rooms' | 'tests';
type DbTableTab = 'users' | 'messages' | 'moderation' | 'grabs' | 'vault';

const SAMPLE_QUICK_COMMANDS = [
  { label: '!triggers', cmd: '!triggers', sender: 'Stonerwayne1000' },
  { label: '!chat (Enable Chat)', cmd: '!chat', sender: 'Stonerwayne1000' },
  { label: '!info on Stonerwayne1000', cmd: '!info on Stonerwayne1000', sender: 'Rosie' },
  { label: '!who is irreplacable', cmd: '!who is irreplacable', sender: 'Stonerwayne1000' },
  { label: '!grabs 24h', cmd: '!grabs 24h', sender: 'nico1ee' },
  { label: 'who kicked tedi4300?', cmd: 'who kicked tedi4300?', sender: 'Stonerwayne1000' },
  { label: '!suppress (Vault)', cmd: '!suppress', sender: 'Rosie' },
  { label: '!unsuppress (Restore)', cmd: '!unsuppress', sender: 'Rosie' },
  { label: '!diss WutUpWattz', cmd: '!diss WutUpWattz', sender: 'Stonerwayne1000' },
  { label: '!unban User_2 (Mod Check)', cmd: '!unban User_2', sender: 'skracH_iLL_Man_' },
];

export function App() {
  const [engine] = useState(() => new CamfrogBotEngine());
  const [version, setVersion] = useState(0);
  const bump = () => setVersion((v) => v + 1);

  const [activeSection, setActiveSection] = useState<ActiveSection>('monitor');
  const [dbTab, setDbTab] = useState<DbTableTab>('users');
  const [roomFilter, setRoomFilter] = useState<RoomName | 'ALL'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  // Chat simulator inputs
  const [senderInput, setSenderInput] = useState('Stonerwayne1000');
  const [messageInput, setMessageInput] = useState('!info on Stonerwayne1000');
  const [selectedRoom, setSelectedRoom] = useState<RoomName>('Players__Lounge');

  // Moderation & Mic grab simulator inputs
  const [modRawInput, setModRawInput] = useState('Mod_Alpha kicked Troll_99.');
  const [micUserInput, setMicUserInput] = useState('Stonerwayne1000');
  const [micDurationInput, setMicDurationInput] = useState('35');
  const [operatorInput, setOperatorInput] = useState('');

  // UIA Coordinate tester
  const [probeX, setProbeX] = useState('1550');
  const [probeY, setProbeY] = useState('54');

  // Unit tests state
  const [testResults, setTestResults] = useState<TestCaseResult[]>(() => runOfflineBotTests());

  // Derive live state from engine (re-evaluated on version bump)
  const usersList = useMemo(() => Array.from(engine.store.users.values()), [engine, version]);
  const messagesList = useMemo(() => [...engine.store.messages].reverse(), [engine, version]);
  const moderationList = useMemo(() => [...engine.store.moderationEvents].reverse(), [engine, version]);
  const micGrabsList = useMemo(() => [...engine.store.micGrabs].reverse(), [engine, version]);
  const suppressedList = useMemo(() => Array.from(engine.store.suppressedVault.values()), [engine, version]);

  const filteredMessages = useMemo(() => {
    return messagesList.filter((m) => {
      if (roomFilter !== 'ALL' && m.room && m.room !== roomFilter) return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        return m.username.toLowerCase().includes(q) || m.body.toLowerCase().includes(q);
      }
      return true;
    });
  }, [messagesList, roomFilter, searchQuery]);

  // Simulated UIA Control Tree nodes matching ui_automation.py expectations
  const uiaNodes: UIANode[] = useMemo(() => {
    const baseNodes: UIANode[] = [
      {
        id: 'win-root',
        control_type: 'Window',
        name: `${engine.currentRoom} - Video Chat Room`,
        class_name: 'CamfrogRoomWindow',
        left: 100,
        top: 20,
        right: 1820,
        bottom: 1020,
      },
      {
        id: 'tab-roomlist',
        control_type: 'Button',
        name: 'Room List',
        class_name: 'CTabButton',
        left: 1313,
        top: 37,
        right: 1473,
        bottom: 71,
      },
      {
        id: 'tab-players',
        control_type: 'Button',
        name: 'Players__Lounge',
        class_name: 'CTabButton',
        left: 1473,
        top: 37,
        right: 1633,
        bottom: 71,
      },
      {
        id: 'tab-drama',
        control_type: 'Button',
        name: 'Drama_Central',
        class_name: 'CTabButton',
        left: 1633,
        top: 37,
        right: 1793,
        bottom: 71,
      },
      {
        id: 'btn-talk',
        control_type: 'Button',
        name: 'Talk',
        class_name: 'CButtonTS',
        left: 1460,
        top: 860,
        right: 1540,
        bottom: 892,
      },
      {
        id: 'speaker-active',
        control_type: 'Custom',
        name: engine.activeSpeaker || '',
        class_name: 'CButtonTS',
        left: 1555,
        top: 862,
        right: 1720,
        bottom: 890,
      },
      {
        id: 'chrome-ignored',
        control_type: 'Text',
        name: 'GIFTUsers2',
        class_name: 'CEFToolbarLabel',
        left: 1460,
        top: 110,
        right: 1620,
        bottom: 134,
      },
      {
        id: 'edit-chat',
        control_type: 'Edit',
        name: 'Chat Input Box',
        class_name: 'CEFEditControl',
        left: 120,
        top: 930,
        right: 1420,
        bottom: 985,
      },
    ];

    usersList.slice(0, 8).forEach((u, idx) => {
      baseNodes.push({
        id: `roster-${u.username}`,
        control_type: 'ListItem',
        name: u.username,
        class_name: 'CRosterItem',
        left: 1460,
        top: 160 + idx * 28,
        right: 1790,
        bottom: 184 + idx * 28,
      });
    });

    return baseNodes;
  }, [engine.currentRoom, engine.activeSpeaker, usersList]);

  const handleSendChat = (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageInput.trim() || !senderInput.trim()) return;
    engine.currentRoom = selectedRoom;
    engine.handleMessage(senderInput.trim(), messageInput.trim(), undefined, selectedRoom);
    setMessageInput('');
    bump();
  };

  const handleQuickCommand = (sender: string, cmd: string) => {
    setSenderInput(sender);
    engine.currentRoom = selectedRoom;
    engine.handleMessage(sender, cmd, undefined, selectedRoom);
    bump();
  };

  const handleInjectModeration = (e: React.FormEvent) => {
    e.preventDefault();
    if (!modRawInput.trim()) return;
    engine.handleMessage('System_Notice', modRawInput.trim(), undefined, selectedRoom);
    bump();
  };

  const handleLogMicGrab = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = cleanUsername(micUserInput);
    const dur = parseFloat(micDurationInput);
    if (!cleaned || Number.isNaN(dur) || dur <= 0) return;
    engine.store.recordMicGrab(cleaned, dur);
    engine.activeSpeaker = cleaned;
    bump();
  };

  const handleSimulatePresence = (action: 'join' | 'quit') => {
    const cleaned = cleanUsername(senderInput);
    if (!cleaned) return;
    const key = `${cleaned}:${action}:${Date.now()}`;
    engine.store.recordPresence(cleaned, action, key, selectedRoom);
    bump();
  };

  const handleSwitchRoomByTab = (room: RoomName) => {
    engine.currentRoom = room;
    setSelectedRoom(room);
    bump();
  };

  const detectedRoomAtProbe = useMemo(() => {
    const x = parseInt(probeX, 10);
    const y = parseInt(probeY, 10);
    if (Number.isNaN(x) || Number.isNaN(y)) return null;
    for (const [roomName, [left, top, right, bottom]] of Object.entries(ROOM_TAB_POSITIONS)) {
      if (x >= left && x <= right && y >= top && y <= bottom) {
        return roomName as RoomName;
      }
    }
    return null;
  }, [probeX, probeY]);

  const parsedModerationPreview = useMemo(() => detectModeration(modRawInput), [modRawInput]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Bar Contract: 3 Zones (Single-element Brand, 5 Nav Links, 2 Primary Actions) */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-900/80 sticky top-0 z-20">
        <a
          href="#monitor"
          onClick={(e) => {
            e.preventDefault();
            setActiveSection('monitor');
          }}
          className="font-display text-lg font-bold tracking-tight text-white whitespace-nowrap"
        >
          Camfrog UIA Bot
        </a>

        <nav className="hidden md:flex items-center gap-6 text-sm font-medium text-slate-300">
          <button
            type="button"
            onClick={() => setActiveSection('monitor')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'monitor'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Live Monitor
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('database')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'database'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            SQLite &amp; Vault
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('uia')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'uia'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            UIA Tree Inspector
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('rooms')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'rooms'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Multi-Room Tabs
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('tests')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'tests'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Verification Suite
          </button>
        </nav>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              engine.settings.dry_run = !engine.settings.dry_run;
              bump();
            }}
            className={`px-4 py-2 text-xs font-medium rounded-lg border transition-colors whitespace-nowrap ${
              engine.settings.dry_run
                ? 'bg-amber-500/10 border-amber-500/40 text-amber-200 hover:bg-amber-500/20'
                : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-200 hover:bg-emerald-500/20'
            }`}
          >
            {engine.settings.dry_run ? 'Mode: --dry-run (Safe)' : 'Mode: Live UIA Send'}
          </button>
          <button
            type="button"
            onClick={() => {
              setTestResults(runOfflineBotTests());
              setActiveSection('tests');
            }}
            className="px-4 py-2 text-xs font-medium text-slate-950 bg-emerald-400 rounded-lg hover:bg-emerald-300 transition-colors whitespace-nowrap"
          >
            Run Self-Tests
          </button>
        </div>
      </header>

      {/* Mobile Navigation Bar */}
      <div className="flex md:hidden items-center gap-2 px-4 py-2.5 border-b border-slate-800 bg-slate-900 overflow-x-auto">
        {(['monitor', 'database', 'uia', 'rooms', 'tests'] as ActiveSection[]).map((sec) => (
          <button
            key={sec}
            type="button"
            onClick={() => setActiveSection(sec)}
            className={`px-3 py-1.5 text-xs font-medium rounded-md whitespace-nowrap ${
              activeSection === sec ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
            }`}
          >
            {sec === 'monitor' && 'Live Monitor'}
            {sec === 'database' && 'SQLite & Vault'}
            {sec === 'uia' && 'UIA Tree'}
            {sec === 'rooms' && 'Room Tabs'}
            {sec === 'tests' && 'Tests'}
          </button>
        ))}
      </div>

      {/* Main Content Container */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-8 space-y-8">
        {/* Top Summary Strip — Clean unboxed metadata + tabular figures */}
        <section className="border-b border-slate-800 pb-6 flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 font-mono">
              <span>Backend: pywinauto (uia)</span>
              <span aria-hidden="true">·</span>
              <span>OCR / DXCam / Tesseract: Disabled</span>
              <span aria-hidden="true">·</span>
              <span>Active Room: {engine.currentRoom}</span>
              <span aria-hidden="true">·</span>
              <span>Speaker: {engine.activeSpeaker || 'Idle'}</span>
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Camfrog UI-Automation Bot &amp; Room Processor
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              Reads chat events, presence updates, and strict moderation notices directly from Camfrog&apos;s Windows UI
              Automation accessibility tree without screen capture or pixel guessing.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-800">
            <div>
              <div className="text-xs text-slate-400">Tracked Users</div>
              <div className="text-2xl font-semibold text-white font-mono tabular-nums mt-0.5">{usersList.length}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Logged Messages</div>
              <div className="text-2xl font-semibold text-white font-mono tabular-nums mt-0.5">
                {messagesList.length}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Moderation Notices</div>
              <div className="text-2xl font-semibold text-white font-mono tabular-nums mt-0.5">
                {moderationList.length}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Suppressed Vault</div>
              <div className="text-2xl font-semibold text-amber-300 font-mono tabular-nums mt-0.5">
                {suppressedList.length}
              </div>
            </div>
          </div>
        </section>

        {/* SECTION 1: LIVE MONITOR & COMMAND DISPATCHER */}
        {activeSection === 'monitor' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left 8 Columns: Chat Stream + Event Simulator */}
            <div className="lg:col-span-8 space-y-6">
              {/* Interactive Stream Console */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-white">01. Live UIA Event Stream &amp; Command Dispatcher</h2>
                    <div className="flex items-center gap-2 text-xs text-slate-400 mt-1">
                      <span>Poll Interval: {POLL_INTERVAL_SECONDS}s</span>
                      <span aria-hidden="true">·</span>
                      <span>Max Message Length: {MAX_CHAT_MESSAGE_LENGTH} chars</span>
                      <span aria-hidden="true">·</span>
                      <span>Chat Mode: {engine.settings.chat_mode ? 'On' : 'Off'}</span>
                      <span aria-hidden="true">·</span>
                      <span>Silent Mode: {engine.settings.silent_mode ? 'Muted' : 'Active'}</span>
                    </div>
                  </div>

                  {/* Interactive Room Filter Control */}
                  <div className="flex items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg self-start">
                    {(['ALL', 'Players__Lounge', 'Drama_Central', 'Room List'] as const).map((r) => (
                      <button
                        key={r}
                        type="button"
                        onClick={() => setRoomFilter(r)}
                        className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors whitespace-nowrap ${
                          roomFilter === r ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                        }`}
                      >
                        {r === 'ALL' ? 'All Rooms' : r}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Quick Trigger Bar */}
                <div className="space-y-2">
                  <div className="text-xs text-slate-400">
                    Click any documented trigger below to dispatch a simulated UIA chat event immediately:
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {SAMPLE_QUICK_COMMANDS.map((item) => (
                      <button
                        key={item.label}
                        type="button"
                        onClick={() => handleQuickCommand(item.sender, item.cmd)}
                        className="px-3 py-1.5 text-xs font-mono bg-slate-950 hover:bg-slate-800 text-slate-200 border border-slate-800 rounded-md transition-colors whitespace-nowrap"
                      >
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Chat Event Feed */}
                <div className="border border-slate-800 rounded-lg bg-slate-950 divide-y divide-slate-800/70 max-h-[420px] overflow-y-auto">
                  {filteredMessages.length === 0 ? (
                    <div className="p-8 text-center text-sm text-slate-400">
                      No UIA chat messages match the active filter. Dispatch a trigger or clear the filter.
                    </div>
                  ) : (
                    filteredMessages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`px-4 py-3 text-sm flex flex-col sm:flex-row sm:items-baseline justify-between gap-2 ${
                          msg.is_bot_reply ? 'bg-emerald-950/20' : 'hover:bg-slate-900/40'
                        }`}
                      >
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                            <span className={msg.is_bot_reply ? 'text-emerald-300 font-semibold' : 'text-slate-200 font-semibold'}>
                              {msg.username}
                            </span>
                            <span aria-hidden="true">·</span>
                            <span>{msg.room || 'Players__Lounge'}</span>
                            <span aria-hidden="true">·</span>
                            <span>{msg.room_time}</span>
                            {msg.is_bot_reply && (
                              <>
                                <span aria-hidden="true">·</span>
                                <span className="text-emerald-400">
                                  {msg.dry_run ? 'UIA Dry-Run Reply' : 'UIA Dispatched Reply'}
                                </span>
                              </>
                            )}
                          </div>
                          <p className="text-slate-100 break-words font-mono text-xs sm:text-sm">{msg.body}</p>
                        </div>
                        <span className="text-[11px] font-mono text-slate-500 shrink-0 tabular-nums">
                          #{msg.id} · {msg.event_key.slice(0, 8)}
                        </span>
                      </div>
                    ))
                  )}
                </div>

                {/* Message Input Form */}
                <form onSubmit={handleSendChat} className="grid grid-cols-1 sm:grid-cols-12 gap-3 pt-2">
                  <div className="sm:col-span-3">
                    <label className="block text-xs text-slate-400 mb-1">Room Tab</label>
                    <select
                      value={selectedRoom}
                      onChange={(e) => setSelectedRoom(e.target.value as RoomName)}
                      className="w-full px-3 py-2 text-sm bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-400"
                    >
                      <option value="Players__Lounge">Players__Lounge</option>
                      <option value="Drama_Central">Drama_Central</option>
                      <option value="Room List">Room List</option>
                    </select>
                  </div>
                  <div className="sm:col-span-3">
                    <label className="block text-xs text-slate-400 mb-1">Sender Username</label>
                    <input
                      type="text"
                      value={senderInput}
                      onChange={(e) => setSenderInput(e.target.value)}
                      placeholder="Stonerwayne1000"
                      className="w-full px-3 py-2 text-sm font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-400"
                    />
                  </div>
                  <div className="sm:col-span-4">
                    <label className="block text-xs text-slate-400 mb-1">Chat Text or !Trigger</label>
                    <input
                      type="text"
                      value={messageInput}
                      onChange={(e) => setMessageInput(e.target.value)}
                      placeholder="Type a message or !info on <user>..."
                      className="w-full px-3 py-2 text-sm font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-400"
                    />
                  </div>
                  <div className="sm:col-span-2 flex items-end">
                    <button
                      type="submit"
                      className="w-full px-4 py-2 text-sm font-medium bg-emerald-400 text-slate-950 rounded-lg hover:bg-emerald-300 transition-colors flex items-center justify-center gap-1.5 whitespace-nowrap"
                    >
                      <Send className="w-4 h-4" />
                      Send
                    </button>
                  </div>
                </form>
              </div>
            </div>

            {/* Right 4 Columns: Bot Settings & Event Injectors */}
            <div className="lg:col-span-4 space-y-6">
              {/* Bot Runtime Settings */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">02. Bot Runtime Switches</h2>
                <p className="text-xs text-slate-400">
                  Direct state controls mirroring <code className="text-slate-200">BOT_SETTINGS</code> in{' '}
                  <code className="text-slate-200">config.py</code>.
                </p>

                <div className="divide-y divide-slate-800 text-sm">
                  <div className="py-3 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-slate-200">Chat Mode (!chat / !chatoff)</div>
                      <div className="text-xs text-slate-400">Enables kaekae replies, tone &amp; diss scheduler</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        engine.settings.chat_mode = !engine.settings.chat_mode;
                        bump();
                      }}
                      className={`px-3 py-1.5 text-xs font-mono rounded-md border whitespace-nowrap ${
                        engine.settings.chat_mode
                          ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-200'
                          : 'bg-slate-950 border-slate-800 text-slate-400'
                      }`}
                    >
                      {engine.settings.chat_mode ? 'ENABLED' : 'OFF'}
                    </button>
                  </div>

                  <div className="py-3 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-slate-200">Silent Switch (!shutup)</div>
                      <div className="text-xs text-slate-400">Keep recording UIA events without replying</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        engine.settings.silent_mode = !engine.settings.silent_mode;
                        bump();
                      }}
                      className={`px-3 py-1.5 text-xs font-mono rounded-md border whitespace-nowrap ${
                        engine.settings.silent_mode
                          ? 'bg-amber-500/20 border-amber-500/50 text-amber-200'
                          : 'bg-slate-950 border-slate-800 text-slate-400'
                      }`}
                    >
                      {engine.settings.silent_mode ? 'SILENT' : 'SPEAKING'}
                    </button>
                  </div>

                  <div className="py-3 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-slate-200">Presence Simulation</div>
                      <div className="text-xs text-slate-400">Emit UIA Join: / Quit: for {senderInput || 'user'}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleSimulatePresence('join')}
                        className="px-2.5 py-1.5 text-xs font-mono bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-md text-emerald-300 flex items-center gap-1 whitespace-nowrap"
                      >
                        <UserPlus className="w-3.5 h-3.5" />
                        Join
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSimulatePresence('quit')}
                        className="px-2.5 py-1.5 text-xs font-mono bg-slate-950 hover:bg-slate-800 border border-slate-800 rounded-md text-slate-300 flex items-center gap-1 whitespace-nowrap"
                      >
                        <UserMinus className="w-3.5 h-3.5" />
                        Quit
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Strict Moderation Notice Tester */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">03. Moderation Notice Parser</h2>
                <p className="text-xs text-slate-400">
                  Tests <code className="text-slate-200">detect_moderation()</code> regex rules. Conversational prose is
                  rejected; strict room notices are logged to <code className="text-slate-200">moderation_events</code>.
                </p>

                <form onSubmit={handleInjectModeration} className="space-y-3">
                  <input
                    type="text"
                    value={modRawInput}
                    onChange={(e) => setModRawInput(e.target.value)}
                    className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-400"
                  />
                  <div className="text-xs font-mono p-2.5 rounded-lg bg-slate-950 border border-slate-800">
                    {parsedModerationPreview ? (
                      <span className="text-emerald-300">
                        MATCH: actor=&quot;{parsedModerationPreview.actor}&quot; · action=&quot;
                        {parsedModerationPreview.action}&quot; · target=&quot;{parsedModerationPreview.target}&quot;
                      </span>
                    ) : (
                      <span className="text-amber-300">
                        REJECTED: Treated as regular chat prose (not a moderation notice)
                      </span>
                    )}
                  </div>
                  <button
                    type="submit"
                    className="w-full px-4 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors whitespace-nowrap"
                  >
                    Dispatch Line Into Bot
                  </button>
                </form>
              </div>

              {/* Mic Grab Simulator */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">04. Active Speaker &amp; Mic Grabs</h2>
                <p className="text-xs text-slate-400">
                  Simulates <code className="text-slate-200">CButtonTS</code> active speaker detection to the right of
                  the Talk button and records <code className="text-slate-200">mic_grabs</code> duration.
                </p>
                <form onSubmit={handleLogMicGrab} className="grid grid-cols-12 gap-2">
                  <input
                    type="text"
                    value={micUserInput}
                    onChange={(e) => setMicUserInput(e.target.value)}
                    placeholder="Username"
                    className="col-span-6 px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                  />
                  <input
                    type="number"
                    value={micDurationInput}
                    onChange={(e) => setMicDurationInput(e.target.value)}
                    placeholder="Sec"
                    className="col-span-3 px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                  />
                  <button
                    type="submit"
                    className="col-span-3 px-3 py-2 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white rounded-lg transition-colors whitespace-nowrap"
                  >
                    Log Grab
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 2: SQLITE DATABASE & SUPPRESSION VAULT */}
        {activeSection === 'database' && (
          <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">SQLite Persistence &amp; Non-Queryable Suppression Vault</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Inspecting <code className="text-slate-200">data/camfrog_bot.db</code> tables and{' '}
                  <code className="text-slate-200">data/suppressed/*.json</code> vault files.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-1 p-1 bg-slate-950 border border-slate-800 rounded-lg">
                {(
                  [
                    { id: 'users', label: `bot_users (${usersList.length})` },
                    { id: 'messages', label: `bot_messages (${messagesList.length})` },
                    { id: 'moderation', label: `moderation_events (${moderationList.length})` },
                    { id: 'grabs', label: `mic_grabs (${micGrabsList.length})` },
                    { id: 'vault', label: `suppressed_users (${suppressedList.length})` },
                  ] as const
                ).map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => setDbTab(t.id)}
                    className={`px-3 py-1.5 text-xs font-mono rounded-md transition-colors whitespace-nowrap ${
                      dbTab === t.id ? 'bg-slate-800 text-white' : 'text-slate-400 hover:text-white'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            {dbTab === 'users' && (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 font-mono">
                      <th className="py-2.5 px-3">username</th>
                      <th className="py-2.5 px-3">first_seen</th>
                      <th className="py-2.5 px-3">last_seen</th>
                      <th className="py-2.5 px-3 text-right">message_count</th>
                      <th className="py-2.5 px-3 text-right">active</th>
                      <th className="py-2.5 px-3 text-right">Vault Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {usersList.map((u) => (
                      <tr key={u.username} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 font-semibold text-white">{u.username}</td>
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{u.first_seen}</td>
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{u.last_seen}</td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">{u.message_count}</td>
                        <td className="py-2.5 px-3 text-right text-slate-300 tabular-nums">
                          {u.active === 1 ? '1 (Active)' : '0 (Quit)'}
                        </td>
                        <td className="py-2.5 px-3 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              engine.store.suppress(u.username);
                              bump();
                            }}
                            className="px-2.5 py-1 text-xs bg-slate-950 hover:bg-slate-800 text-amber-300 border border-slate-800 rounded whitespace-nowrap"
                          >
                            !suppress
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {dbTab === 'messages' && (
              <div className="space-y-4">
                <div className="flex items-center gap-2 max-w-md">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Filter bot_messages by username or text..."
                    className="w-full px-3 py-1.5 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                  />
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse text-sm">
                    <thead>
                      <tr className="border-b border-slate-800 text-xs text-slate-400 font-mono">
                        <th className="py-2.5 px-3">id</th>
                        <th className="py-2.5 px-3">username</th>
                        <th className="py-2.5 px-3">body</th>
                        <th className="py-2.5 px-3">room_time</th>
                        <th className="py-2.5 px-3">event_key (sha256)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                      {filteredMessages.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-900/60">
                          <td className="py-2.5 px-3 text-slate-400 tabular-nums">{m.id}</td>
                          <td className="py-2.5 px-3 font-semibold text-white">{m.username}</td>
                          <td className="py-2.5 px-3 text-slate-200">{m.body}</td>
                          <td className="py-2.5 px-3 text-slate-400 tabular-nums">{m.room_time}</td>
                          <td className="py-2.5 px-3 text-slate-500 tabular-nums">{m.event_key}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {dbTab === 'moderation' && (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 font-mono">
                      <th className="py-2.5 px-3">id</th>
                      <th className="py-2.5 px-3">actor</th>
                      <th className="py-2.5 px-3">action</th>
                      <th className="py-2.5 px-3">target</th>
                      <th className="py-2.5 px-3">raw_text</th>
                      <th className="py-2.5 px-3">observed_at</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {moderationList.map((ev) => (
                      <tr key={ev.id} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{ev.id}</td>
                        <td className="py-2.5 px-3 text-emerald-300 font-semibold">{ev.actor}</td>
                        <td className="py-2.5 px-3 text-amber-300">{ev.action}</td>
                        <td className="py-2.5 px-3 text-white font-semibold">{ev.target}</td>
                        <td className="py-2.5 px-3 text-slate-300">{ev.raw_text}</td>
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{ev.observed_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {dbTab === 'grabs' && (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 font-mono">
                      <th className="py-2.5 px-3">id</th>
                      <th className="py-2.5 px-3">username</th>
                      <th className="py-2.5 px-3 text-right">duration_seconds</th>
                      <th className="py-2.5 px-3">started_at</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {micGrabsList.map((g) => (
                      <tr key={g.id} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{g.id}</td>
                        <td className="py-2.5 px-3 text-white font-semibold">{g.username}</td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 tabular-nums">{g.duration_seconds}s</td>
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{g.started_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {dbTab === 'vault' && (
              <div className="space-y-4">
                {suppressedList.length === 0 ? (
                  <div className="p-8 text-center text-sm text-slate-400 border border-slate-800 rounded-lg bg-slate-950">
                    No users are currently suppressed. Run <code className="text-slate-200">!suppress</code> from any
                    user or click <code className="text-slate-200">!suppress</code> in the{' '}
                    <code className="text-slate-200">bot_users</code> tab to move their history to{' '}
                    <code className="text-slate-200">data/suppressed/</code>.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-950">
                    {suppressedList.map((vault) => (
                      <div key={vault.username} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1 font-mono text-xs">
                          <div className="text-amber-300 font-semibold">{vault.username} (Suppressed)</div>
                          <div className="text-slate-400">
                            Vault Path: {vault.vault_file} · Suppressed At: {vault.suppressed_at} · Archived Messages:{' '}
                            {vault.messages.length} · Archived Grabs: {vault.mic_grabs.length}
                          </div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            engine.store.unsuppress(vault.username);
                            bump();
                          }}
                          className="px-3 py-1.5 text-xs font-mono bg-emerald-400 text-slate-950 font-semibold rounded-md hover:bg-emerald-300 transition-colors whitespace-nowrap"
                        >
                          !unsuppress (Restore Vault)
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* SECTION 3: UIA ACCESSIBILITY TREE & USERNAME FILTER */}
        {activeSection === 'uia' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-8 border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-lg font-semibold text-white">Live UIA / CEF Control Tree Nodes</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Window regex: <code className="text-slate-200 font-mono">{CAMFROG_WINDOW_TITLE_RE}</code> · Cache TTL:{' '}
                  <code className="text-slate-200 font-mono">{UIA_CACHE_SECONDS}s</code>
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2.5 px-3">control_type</th>
                      <th className="py-2.5 px-3">class_name</th>
                      <th className="py-2.5 px-3">name</th>
                      <th className="py-2.5 px-3 text-right">bounding_rect (L, T, R, B)</th>
                      <th className="py-2.5 px-3 text-right">clean_username()</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {uiaNodes.map((n) => {
                      const cleaned = cleanUsername(n.name);
                      return (
                        <tr key={n.id} className="hover:bg-slate-900/60">
                          <td className="py-2.5 px-3 text-emerald-300">{n.control_type}</td>
                          <td className="py-2.5 px-3 text-slate-300">{n.class_name}</td>
                          <td className="py-2.5 px-3 text-white">{n.name}</td>
                          <td className="py-2.5 px-3 text-right text-slate-400 tabular-nums">
                            ({n.left}, {n.top}, {n.right}, {n.bottom})
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {cleaned ? (
                              <span className="text-emerald-300">{cleaned}</span>
                            ) : (
                              <span className="text-slate-500">Ignored (UI Chrome)</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="lg:col-span-4 space-y-6">
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">Layout Locations (--locations)</h2>
                <p className="text-xs text-slate-400">
                  Output of <code className="text-slate-200">camfrog_boy.py --dry-run --locations</code> derived from
                  UIA rectangles:
                </p>
                <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
                  {JSON.stringify(
                    {
                      window: [100, 20, 1820, 1020],
                      chat_feed: [100, 20, 1441, 1020],
                      user_list: [1441, 20, 1820, 1020],
                      chat_input: [120, 930, 1420, 985],
                      talk: [1460, 860, 1540, 892],
                    },
                    null,
                    2
                  )}
                </pre>
              </div>

              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">MODERATION_ALLOWED_SENDERS</h2>
                <p className="text-xs text-slate-400">
                  Operators authorized to emit slash commands (<code className="text-slate-200">/unban</code>,{' '}
                  <code className="text-slate-200">/unpunish</code>, <code className="text-slate-200">/unblockmic</code>
                  , <code className="text-slate-200">/topic</code>, <code className="text-slate-200">/watchlist</code>):
                </p>
                <div className="space-y-2 font-mono text-xs">
                  {Array.from(engine.allowedModerationSenders).map((op) => (
                    <div
                      key={op}
                      className="flex items-center justify-between px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg"
                    >
                      <span className="text-slate-200">{op}</span>
                      <button
                        type="button"
                        onClick={() => {
                          engine.allowedModerationSenders.delete(op);
                          bump();
                        }}
                        className="text-slate-400 hover:text-rose-400"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    const cleaned = cleanUsername(operatorInput);
                    if (cleaned) {
                      engine.allowedModerationSenders.add(cleaned.toLowerCase());
                      setOperatorInput('');
                      bump();
                    }
                  }}
                  className="flex gap-2"
                >
                  <input
                    type="text"
                    value={operatorInput}
                    onChange={(e) => setOperatorInput(e.target.value)}
                    placeholder="Add operator username..."
                    className="flex-1 px-3 py-1.5 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                  />
                  <button
                    type="submit"
                    className="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-white rounded-lg whitespace-nowrap"
                  >
                    Add
                  </button>
                </form>
              </div>
            </div>
          </div>
        )}

        {/* SECTION 4: MULTI-ROOM TAB COORDINATES & ROOM DATA PROCESSOR */}
        {activeSection === 'rooms' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-7 border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-5">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-lg font-semibold text-white">Room Tab Coordinate Detection (ROOM_TAB_POSITIONS)</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Configured in <code className="text-slate-200">config.py</code> and{' '}
                  <code className="text-slate-200">ui_automation.py</code> for tab switching and context routing.
                </p>
              </div>

              <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-950">
                {(Object.entries(ROOM_TAB_POSITIONS) as Array<[RoomName, [number, number, number, number]]>).map(
                  ([roomName, [left, top, right, bottom]]) => {
                    const isCurrent = engine.currentRoom === roomName;
                    return (
                      <div key={roomName} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold text-white">{roomName}</span>
                            <span aria-hidden="true" className="text-slate-500">
                              ·
                            </span>
                            <span className="text-xs font-mono text-slate-400 tabular-nums">
                              Bounds: [{left}, {top}, {right}, {bottom}]
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 font-mono">
                            Center click target: ({Math.floor((left + right) / 2)}, {Math.floor((top + bottom) / 2)})
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => handleSwitchRoomByTab(roomName)}
                          className={`px-3 py-1.5 text-xs font-mono rounded-md border transition-colors whitespace-nowrap ${
                            isCurrent
                              ? 'bg-emerald-400 text-slate-950 border-emerald-400 font-semibold'
                              : 'bg-slate-900 hover:bg-slate-800 text-slate-200 border-slate-700'
                          }`}
                        >
                          {isCurrent ? 'Active Room Tab' : 'Switch via UIA Tab Click'}
                        </button>
                      </div>
                    );
                  }
                )}
              </div>

              {/* Coordinate Hit-Tester */}
              <div className="pt-2 space-y-3">
                <h3 className="text-sm font-semibold text-white">Test find_room_by_position(x, y)</h3>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-end">
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">X Coordinate</label>
                    <input
                      type="number"
                      value={probeX}
                      onChange={(e) => setProbeX(e.target.value)}
                      className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 tabular-nums"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Y Coordinate</label>
                    <input
                      type="number"
                      value={probeY}
                      onChange={(e) => setProbeY(e.target.value)}
                      className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 tabular-nums"
                    />
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
                    Result:{' '}
                    {detectedRoomAtProbe ? (
                      <span className="text-emerald-300 font-semibold">{detectedRoomAtProbe}</span>
                    ) : (
                      <span className="text-amber-300">None (Outside tab bounds)</span>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="lg:col-span-5 border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
              <h2 className="text-lg font-semibold text-white">Documented Trigger Reference</h2>
              <p className="text-xs text-slate-400">
                All triggers defined in <code className="text-slate-200">TRIGGER_NAMES</code> in{' '}
                <code className="text-slate-200">config.py</code>:
              </p>
              <div className="grid grid-cols-2 gap-2 font-mono text-xs">
                {TRIGGER_NAMES.map((trig) => (
                  <div key={trig} className="px-3 py-2 bg-slate-950 border border-slate-800 rounded text-slate-200">
                    {trig}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* SECTION 5: OFFLINE UNIT TEST SUITE (test_bot.py) */}
        {activeSection === 'tests' && (
          <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Offline Unit Test Suite (test_bot.py)</h2>
                <p className="text-xs text-slate-400 mt-1">
                  Executes the 4 unit tests from <code className="text-slate-200">test_bot.py</code> against the
                  in-memory <code className="text-slate-200">CamfrogBotEngine</code> and{' '}
                  <code className="text-slate-200">CamfrogStore</code>.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setTestResults(runOfflineBotTests())}
                className="px-4 py-2 text-xs font-medium bg-emerald-400 text-slate-950 rounded-lg hover:bg-emerald-300 transition-colors flex items-center gap-1.5 self-start whitespace-nowrap"
              >
                <RefreshCw className="w-3.5 h-3.5" />
                Re-run All Tests
              </button>
            </div>

            <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-950">
              {testResults.map((test) => (
                <div key={test.name} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      {test.passed ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                      ) : (
                        <XCircle className="w-4 h-4 text-rose-400 shrink-0" />
                      )}
                      <span className="font-mono text-sm font-semibold text-white">{test.name}</span>
                      <span aria-hidden="true" className="text-slate-500">
                        ·
                      </span>
                      <span className={`text-xs font-mono ${test.passed ? 'text-emerald-300' : 'text-rose-300'}`}>
                        {test.passed ? 'PASSED' : 'FAILED'}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300">{test.description}</p>
                    <p className="text-xs font-mono text-slate-400">Output: {test.details}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
