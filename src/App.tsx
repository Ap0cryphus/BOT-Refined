import React, { useState, useMemo, useEffect, useRef } from 'react';
import {
  CamfrogBotEngine,
  ROOM_TAB_POSITIONS,
  ROOM_TAB_CLICK_POINTS,
  CALIBRATED_UIA_RECTS,
  BOT_USERNAME,
  MIC_CONFIRM_PERSIST_SECONDS,
  MAX_ROOM_USERS,
  USER_LIST_ITEM_X_SPAN,
  RoomName,
  UIANode,
  cleanUsername,
  detectModeration,
  runOfflineBotTests,
  TestCaseResult,
  TRIGGER_NAMES,
} from './lib/camfrogBot';
import {
  Send,
  Mic,
  MicOff,
  UserPlus,
  UserMinus,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Search,
  Radio,
  Copy,
  Download,
  Check,
} from 'lucide-react';
import {
  FIXED_CONFIG_PY,
  FIXED_UI_AUTOMATION_PY,
  FIXED_CAMFROG_BOT_PY,
  FIXED_ROOM_MONITOR_PY,
  FIXED_ROOM_DATA_PROCESSOR_PY,
  FIXED_TEST_BOT_PY,
} from './lib/pythonFiles';

type ActiveSection = 'monitor' | 'database' | 'uia' | 'rooms' | 'tests' | 'python_fix';
type DbTableTab = 'users' | 'messages' | 'transcripts' | 'moderation' | 'grabs' | 'vault';

const SAMPLE_QUICK_COMMANDS = [
  { label: '!triggers', cmd: '!triggers', sender: 'Stonerwayne1000' },
  { label: '!transcribe (Audio On)', cmd: '!transcribe', sender: 'Stonerwayne1000' },
  { label: '!info on Stonerwayne1000', cmd: '!info on Stonerwayne1000', sender: 'Rosie' },
  { label: '!who is Stonerwayne1000', cmd: '!who is Stonerwayne1000', sender: 'Rosie' },
  { label: '!grabs 24h', cmd: '!grabs 24h', sender: 'nico1ee' },
  { label: 'who kicked tedi4300?', cmd: 'who kicked tedi4300?', sender: 'Stonerwayne1000' },
  { label: '!suppress (Vault)', cmd: '!suppress', sender: 'Rosie' },
  { label: '!unsuppress (Restore)', cmd: '!unsuppress', sender: 'Rosie' },
  { label: '!say Welcome to Players Lounge', cmd: '!say Welcome to Players Lounge', sender: 'Stonerwayne1000' },
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

  // Moderation & Mic grab / Audio transcription simulator inputs
  const [modRawInput, setModRawInput] = useState('Mod_Alpha kicked Troll_99.');
  const [micUserInput, setMicUserInput] = useState('Stonerwayne1000');
  const [micDurationInput, setMicDurationInput] = useState('24');
  const [micTranscriptInput, setMicTranscriptInput] = useState(
    'Everyone on cam gets color in Players Lounge, keep the vibes good.'
  );
  const [operatorInput, setOperatorInput] = useState('');

  // Continuous live browser microphone Speech-to-Text recording state
  const [isLiveListening, setIsLiveListening] = useState(false);
  const [liveInterimText, setLiveInterimText] = useState('');
  const [speechError, setSpeechError] = useState('');
  const recognitionRef = useRef<any>(null);
  const listenStartRef = useRef<number>(0);

  // Hold-to-Talk button [l=1291,t=1169,r=1361,b=1195] state
  const [isHoldingTalk, setIsHoldingTalk] = useState(false);
  const holdStartRef = useRef<number>(0);

  // UIA Coordinate tester defaulted to (1550, 50) -> Players__Lounge
  const [probeX, setProbeX] = useState('1550');
  const [probeY, setProbeY] = useState('50');

  // Unit tests state
  const [testResults, setTestResults] = useState<TestCaseResult[]>(() => runOfflineBotTests());
  const [copiedFile, setCopiedFile] = useState<string>('');

  const handleCopyPython = (filename: string, code: string) => {
    navigator.clipboard.writeText(code);
    setCopiedFile(filename);
    setTimeout(() => setCopiedFile(''), 2000);
  };

  const handleDownloadPython = (filename: string, code: string) => {
    const blob = new Blob([code], { type: 'text/x-python' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Derive live state from engine
  const usersList = useMemo(() => Array.from(engine.store.users.values()), [engine, version]);
  const messagesList = useMemo(() => [...engine.store.messages].reverse(), [engine, version]);
  const transcriptsList = useMemo(() => [...engine.store.audioTranscripts].reverse(), [engine, version]);
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

  // Continuous Web Speech API listener that attributes spoken audio to the active speaker on mic
  const toggleLiveAudioCapture = () => {
    if (isLiveListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
        recognitionRef.current = null;
      }
      setIsLiveListening(false);
      setLiveInterimText('');
      return;
    }

    const SpeechRecognitionCtor =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognitionCtor) {
      setSpeechError(
        'Browser SpeechRecognition API is unavailable in this browser; use the Simulated Continuous Audio Injector below to log transcripts.'
      );
      return;
    }

    try {
      setSpeechError('');
      const recognition = new SpeechRecognitionCtor();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';
      listenStartRef.current = Date.now();

      recognition.onresult = (event: any) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          const res = event.results[i];
          const text = res[0]?.transcript || '';
          if (res.isFinal && text.trim()) {
            const speaker = cleanUsername(engine.activeSpeaker || micUserInput) || 'Active_Speaker';
            const elapsedSec = Math.max(2, Math.round((Date.now() - listenStartRef.current) / 1000));
            listenStartRef.current = Date.now();
            engine.store.recordMicGrab(
              speaker,
              elapsedSec,
              undefined,
              text.trim(),
              engine.currentRoom,
              engine.settings.continuous_audio_store
            );
            bump();
          } else {
            interim += text;
          }
        }
        setLiveInterimText(interim);
      };

      recognition.onerror = (ev: any) => {
        setSpeechError(`Microphone capture notice: ${ev.error || 'stopped'}`);
        setIsLiveListening(false);
      };

      recognition.onend = () => {
        setIsLiveListening(false);
        setLiveInterimText('');
      };

      recognition.start();
      recognitionRef.current = recognition;
      setIsLiveListening(true);
    } catch (err) {
      setSpeechError(`Could not start microphone recognition: ${String(err)}`);
    }
  };

  useEffect(() => {
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, []);

  // Calibrated UIA Control Tree nodes matching exact coordinates provided by user
  const uiaNodes: UIANode[] = useMemo(() => {
    const baseNodes: UIANode[] = [
      {
        id: 'tab-roomlist',
        control_type: 'Button(50000)',
        name: 'Room List Tab (Click @ 1390, 50)',
        class_name: 'CTabButton',
        left: 1313,
        top: 37,
        right: 1473,
        bottom: 71,
        focusable: true,
      },
      {
        id: 'tab-players',
        control_type: 'Button(50000)',
        name: 'Players__Lounge Tab (Click @ 1550, 50)',
        class_name: 'CTabButton',
        left: 1473,
        top: 37,
        right: 1633,
        bottom: 71,
        focusable: true,
      },
      {
        id: 'pane-chat',
        control_type: CALIBRATED_UIA_RECTS.chat_window.control_type,
        name: 'Chat Window Pane (Users Text & Moderation)',
        class_name: 'CEFPaneControl',
        left: CALIBRATED_UIA_RECTS.chat_window.rect[0],
        top: CALIBRATED_UIA_RECTS.chat_window.rect[1],
        right: CALIBRATED_UIA_RECTS.chat_window.rect[2],
        bottom: CALIBRATED_UIA_RECTS.chat_window.rect[3],
        focusable: true,
      },
      {
        id: 'text-chat',
        control_type: CALIBRATED_UIA_RECTS.chat_text.control_type,
        name: 'Chat Window Text Stream (Join: / Quit: / Chat / Moderation)',
        class_name: 'CEFTextControl',
        left: CALIBRATED_UIA_RECTS.chat_text.rect[0],
        top: CALIBRATED_UIA_RECTS.chat_text.rect[1],
        right: CALIBRATED_UIA_RECTS.chat_text.rect[2],
        bottom: CALIBRATED_UIA_RECTS.chat_text.rect[3],
        focusable: false,
      },
      {
        id: 'pane-chat-input',
        control_type: CALIBRATED_UIA_RECTS.chat_input.control_type,
        name: 'Chat Txt Field (Bot Input -> Click @ 1946, 1223)',
        class_name: 'CEFChatInputPane',
        left: CALIBRATED_UIA_RECTS.chat_input.rect[0],
        top: CALIBRATED_UIA_RECTS.chat_input.rect[1],
        right: CALIBRATED_UIA_RECTS.chat_input.rect[2],
        bottom: CALIBRATED_UIA_RECTS.chat_input.rect[3],
        focusable: false,
      },
      {
        id: 'list-users',
        control_type: CALIBRATED_UIA_RECTS.user_list.control_type,
        name: `User List Container (Trending [l=${USER_LIST_ITEM_X_SPAN[0]}, r=${USER_LIST_ITEM_X_SPAN[1]}], max ${MAX_ROOM_USERS})`,
        class_name: 'CEFUserList',
        left: CALIBRATED_UIA_RECTS.user_list.rect[0],
        top: CALIBRATED_UIA_RECTS.user_list.rect[1],
        right: CALIBRATED_UIA_RECTS.user_list.rect[2],
        bottom: CALIBRATED_UIA_RECTS.user_list.rect[3],
        focusable: true,
      },
      {
        id: 'btn-talk',
        control_type: CALIBRATED_UIA_RECTS.talk_button.control_type,
        name: 'Talk Button (2 Quick Clicks + Hold to Transmit Audio, Release when Done)',
        class_name: 'CButtonTS',
        left: CALIBRATED_UIA_RECTS.talk_button.rect[0],
        top: CALIBRATED_UIA_RECTS.talk_button.rect[1],
        right: CALIBRATED_UIA_RECTS.talk_button.rect[2],
        bottom: CALIBRATED_UIA_RECTS.talk_button.rect[3],
        focusable: true,
      },
      {
        id: 'speaker-active',
        control_type: CALIBRATED_UIA_RECTS.active_speaker.control_type,
        name: engine.activeSpeaker || '(Idle / Erased from UI Tree — Mic Free)',
        class_name: 'CButtonTS',
        left: CALIBRATED_UIA_RECTS.active_speaker.rect[0],
        top: CALIBRATED_UIA_RECTS.active_speaker.rect[1],
        right: CALIBRATED_UIA_RECTS.active_speaker.rect[2],
        bottom: CALIBRATED_UIA_RECTS.active_speaker.rect[3],
        focusable: true,
      },
      {
        id: 'text-top-gifters',
        control_type: CALIBRATED_UIA_RECTS.top_gifters.control_type,
        name: 'Top Gifters Section (Fallback Text Container)',
        class_name: 'CEFTopGiftersText',
        left: CALIBRATED_UIA_RECTS.top_gifters.rect[0],
        top: CALIBRATED_UIA_RECTS.top_gifters.rect[1],
        right: CALIBRATED_UIA_RECTS.top_gifters.rect[2],
        bottom: CALIBRATED_UIA_RECTS.top_gifters.rect[3],
        focusable: false,
        ignored_reason: 'Top Gifters Overlay [l=1281,t=71,r=2559,b=1160] (Ignored unless fallback)',
      },
      // Dynamic section headers filtered out along trending [l=2359, r=2559]
      {
        id: 'filtered-viewing',
        control_type: 'ListItem(50007)',
        name: 'YOU ARE VIEWING 3',
        class_name: 'ListItem',
        left: 2359,
        top: 141,
        right: 2559,
        bottom: 163,
        ignored_reason: 'Filtered Dynamic Header: "YOU ARE VIEWING #"',
      },
      {
        id: 'filtered-lurkers',
        control_type: 'ListItem(50007)',
        name: 'LURKERS 14',
        class_name: 'ListItem',
        left: 2359,
        top: 480,
        right: 2559,
        bottom: 502,
        ignored_reason: 'Filtered Dynamic Header: "LURKERS #"',
      },
    ];

    usersList.slice(0, 8).forEach((u, idx) => {
      const top = 180 + idx * 24;
      baseNodes.push({
        id: `roster-${u.username}`,
        control_type: 'ListItem(50007)',
        name: u.username,
        class_name: 'ListItem',
        left: 2359,
        top,
        right: 2559,
        bottom: top + 22,
      });
    });

    return baseNodes;
  }, [engine.activeSpeaker, usersList]);

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

  const handleLogMicGrabWithTranscript = (e: React.FormEvent) => {
    e.preventDefault();
    const cleaned = cleanUsername(micUserInput);
    const dur = parseFloat(micDurationInput);
    if (!cleaned || Number.isNaN(dur) || dur <= 0) return;
    engine.store.recordMicGrab(
      cleaned,
      dur,
      undefined,
      micTranscriptInput.trim() || undefined,
      selectedRoom,
      engine.settings.continuous_audio_store
    );
    engine.activeSpeaker = cleaned;
    setMicTranscriptInput('');
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
    const [cx, cy] = ROOM_TAB_CLICK_POINTS[room];
    setProbeX(String(cx));
    setProbeY(String(cy));
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
            Live Monitor &amp; Audio
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
            Calibrated UIA Rects
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
            Tab Coordinates
          </button>
          <button
            type="button"
            onClick={() => setActiveSection('python_fix')}
            className={`py-1 transition-colors whitespace-nowrap ${
              activeSection === 'python_fix'
                ? 'text-white underline underline-offset-8 decoration-emerald-400 decoration-2'
                : 'text-emerald-300 hover:text-white'
            }`}
          >
            Python Fix (AIBot)
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
            {sec === 'monitor' && 'Live & Audio'}
            {sec === 'database' && 'SQLite & Vault'}
            {sec === 'uia' && 'UIA Rects'}
            {sec === 'rooms' && 'Tab Coords'}
            {sec === 'tests' && 'Tests'}
          </button>
        ))}
      </div>

      {/* Main Content Container */}
      <main className="flex-1 max-w-[1400px] w-full mx-auto px-6 py-8 space-y-8">
        {/* Top Summary Strip */}
        <section className="border-b border-slate-800 pb-6 flex flex-col lg:flex-row lg:items-end justify-between gap-6">
          <div className="space-y-2 max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 font-mono">
              <span>Chat Pane/Text: [1281,170,2355,1160]</span>
              <span aria-hidden="true">·</span>
              <span>Chat Input: [1396,1206,2497,1241]</span>
              <span aria-hidden="true">·</span>
              <span>User List: [2359,141,2559,1160]</span>
              <span aria-hidden="true">·</span>
              <span>Talk: [1291,1169,1361,1195]</span>
              <span aria-hidden="true">·</span>
              <span>Active Mic: [1506,1174,1548,1190] ({BOT_USERNAME} {MIC_CONFIRM_PERSIST_SECONDS}s)</span>
            </div>
            <h1 className="font-display text-2xl sm:text-3xl font-bold text-white tracking-tight">
              Camfrog UI-Automation Bot &amp; Continuous Audio Store
            </h1>
            <p className="text-sm text-slate-300 leading-relaxed">
              Combines fixed-coordinate tab switching <code className="text-slate-200">(1390, 50)</code> /{' '}
              <code className="text-slate-200">(1550, 50)</code>, calibrated UIA control rectangles, and continuous
              active-speaker audio transcription stored directly into each user&apos;s recall profile.
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-6 pt-2 lg:pt-0 border-t lg:border-t-0 border-slate-800">
            <div>
              <div className="text-xs text-slate-400">Tracked Users</div>
              <div className="text-2xl font-semibold text-white font-mono tabular-nums mt-0.5">{usersList.length}</div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Chat + Audio Lines</div>
              <div className="text-2xl font-semibold text-white font-mono tabular-nums mt-0.5">
                {messagesList.length}
              </div>
            </div>
            <div>
              <div className="text-xs text-slate-400">Stored Mic Transcripts</div>
              <div className="text-2xl font-semibold text-emerald-300 font-mono tabular-nums mt-0.5">
                {transcriptsList.length}
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

        {/* SECTION 1: LIVE MONITOR, CONTINUOUS AUDIO & COMMAND DISPATCHER */}
        {activeSection === 'monitor' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            {/* Left 8 Columns: Chat Stream + Event Simulator */}
            <div className="lg:col-span-8 space-y-6">
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
                  <div>
                    <h2 className="text-lg font-semibold text-white">01. Pane(50033) &amp; Text(50020) Chat Stream</h2>
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-400 mt-1 font-mono">
                      <span>Chat: [l=1281,t=170,r=2355,b=1160]</span>
                      <span aria-hidden="true">·</span>
                      <span>Input: [l=1396,t=1206,r=2497,b=1241]</span>
                      <span aria-hidden="true">·</span>
                      <span>Active Tab: {engine.currentRoom}</span>
                      <span aria-hidden="true">·</span>
                      <span>Mic [1506,1174,1548,1190]: {engine.activeSpeaker || 'FREE'}</span>
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
                    Click any trigger below to test command recall (including stored mic audio transcripts):
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
                          msg.is_bot_reply
                            ? 'bg-emerald-950/20'
                            : msg.source === 'audio_transcript'
                            ? 'bg-sky-950/20'
                            : 'hover:bg-slate-900/40'
                        }`}
                      >
                        <div className="space-y-1 min-w-0">
                          <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                            <span
                              className={
                                msg.is_bot_reply
                                  ? 'text-emerald-300 font-semibold'
                                  : msg.source === 'audio_transcript'
                                  ? 'text-sky-300 font-semibold'
                                  : 'text-slate-200 font-semibold'
                              }
                            >
                              {msg.username}
                            </span>
                            <span aria-hidden="true">·</span>
                            <span>{msg.room || 'Players__Lounge'}</span>
                            <span aria-hidden="true">·</span>
                            <span>{msg.room_time}</span>
                            {msg.source === 'audio_transcript' && (
                              <>
                                <span aria-hidden="true">·</span>
                                <span className="text-sky-300">Continuous Audio Transcript</span>
                              </>
                            )}
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
                      <option value="Players__Lounge">Players__Lounge (1550, 50)</option>
                      <option value="Room List">Room List (1390, 50)</option>
                      <option value="Drama_Central">Drama_Central</option>
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
                {/* Join: / Quit: Chat Window Presence Simulator */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800/80 text-xs">
                  <span className="text-slate-400 font-mono">
                    Simulate Chat Window <code className="text-slate-200">Join:</code> / <code className="text-slate-200">Quit:</code> for{' '}
                    <span className="text-white font-semibold">{senderInput || 'User'}</span> (tracks room duration):
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleSimulatePresence('join')}
                      className="px-2.5 py-1 font-mono bg-slate-950 hover:bg-slate-800 text-emerald-300 border border-slate-800 rounded flex items-center gap-1"
                    >
                      <UserPlus className="w-3.5 h-3.5" />
                      Join: {senderInput || 'User'}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleSimulatePresence('quit')}
                      className="px-2.5 py-1 font-mono bg-slate-950 hover:bg-slate-800 text-amber-300 border border-slate-800 rounded flex items-center gap-1"
                    >
                      <UserMinus className="w-3.5 h-3.5" />
                      Quit: {senderInput || 'User'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Right 4 Columns: Continuous Audio Capture, Talk Button(50000), & Bot Switches */}
            <div className="lg:col-span-4 space-y-6">
              {/* Continuous Audio Recording & Storage Panel */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-semibold text-white">02. Active Mic [1506,1174,1548,1190]</h2>
                  <span className="text-xs font-mono text-emerald-300">
                    {engine.activeSpeaker ? `ON MIC: ${engine.activeSpeaker}` : 'MIC FREE (ERASED)'}
                  </span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  Watches <code className="text-slate-100">Button(50000) [l=1506,t=1174,r=1548,b=1190]</code> continuously.
                  While a user&apos;s name flows here, speech is transcribed to their profile and the bot will not click Talk.
                  When the name disappears, the bot performs <strong>2 quick clicks + hold</strong> on{' '}
                  <code className="text-slate-100">[l=1291,t=1169,r=1361,b=1195]</code> and waits until{' '}
                  <code className="text-emerald-300">{BOT_USERNAME}</code> persists for{' '}
                  <code className="text-emerald-300">{MIC_CONFIRM_PERSIST_SECONDS}s</code> before broadcasting audio.
                </p>

                <div className="flex items-center justify-between gap-2 p-2.5 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono">
                  <span className="text-slate-300">
                    [1506,1174,1548,1190]:{' '}
                    <strong className={engine.activeSpeaker ? 'text-amber-300' : 'text-emerald-300'}>
                      {engine.activeSpeaker || 'Empty / Erased'}
                    </strong>
                  </span>
                  {engine.activeSpeaker ? (
                    <button
                      type="button"
                      onClick={() => {
                        engine.activeSpeaker = null;
                        if (engine.queuedBroadcasts.length > 0) {
                          const next = engine.queuedBroadcasts.shift()!;
                          engine.sendReply(
                            BOT_USERNAME,
                            `[Mic Freed @ [1506,1174,1548,1190]] 2 quick clicks + hold on [1291,1169,1361,1195], "${BOT_USERNAME}" persisted ${MIC_CONFIRM_PERSIST_SECONDS}s -> Broadcasted: "${next}"`,
                            new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' }),
                            selectedRoom
                          );
                        }
                        bump();
                      }}
                      className="px-2.5 py-1 bg-emerald-400 text-slate-950 font-semibold rounded hover:bg-emerald-300 whitespace-nowrap"
                    >
                      Clear Mic (Erase Node)
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        engine.activeSpeaker = cleanUsername(micUserInput) || 'Stonerwayne1000';
                        bump();
                      }}
                      className="px-2.5 py-1 bg-slate-800 text-slate-200 rounded hover:bg-slate-700 whitespace-nowrap"
                    >
                      Set {cleanUsername(micUserInput) || 'User'} on Mic
                    </button>
                  )}
                </div>

                {/* Live Microphone Speech-to-Text Capture Button */}
                <div className="space-y-2 pt-1">
                  <button
                    type="button"
                    onClick={toggleLiveAudioCapture}
                    className={`w-full px-4 py-2.5 text-xs font-mono font-semibold rounded-lg border transition-colors flex items-center justify-center gap-2 whitespace-nowrap ${
                      isLiveListening
                        ? 'bg-rose-500/20 border-rose-500/50 text-rose-200 hover:bg-rose-500/30'
                        : 'bg-slate-950 border-slate-700 text-emerald-300 hover:bg-slate-800'
                    }`}
                  >
                    {isLiveListening ? (
                      <>
                        <MicOff className="w-4 h-4 text-rose-400" />
                        Stop Live Mic Capture (Recording for {engine.activeSpeaker || micUserInput})
                      </>
                    ) : (
                      <>
                        <Mic className="w-4 h-4 text-emerald-400" />
                        Start Continuous Live Mic Capture (Web Speech)
                      </>
                    )}
                  </button>

                  {liveInterimText && (
                    <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs font-mono text-sky-300">
                      Live hearing ({engine.activeSpeaker || micUserInput}): &quot;{liveInterimText}&quot;
                    </div>
                  )}

                  {speechError && (
                    <div className="p-2.5 rounded bg-slate-950 border border-slate-800 text-xs text-amber-300">
                      {speechError}
                    </div>
                  )}
                </div>

                {/* Simulated Continuous Audio / Mic Grab Injector */}
                <form onSubmit={handleLogMicGrabWithTranscript} className="space-y-3 pt-2 border-t border-slate-800">
                  <div className="text-xs font-medium text-slate-200">
                    Log Active Speaker Audio &amp; Mic Grab to Database
                  </div>
                  <div className="grid grid-cols-12 gap-2">
                    <div className="col-span-8">
                      <label className="block text-[11px] text-slate-400 mb-1">Active Speaker (Right of Talk)</label>
                      <input
                        type="text"
                        value={micUserInput}
                        onChange={(e) => setMicUserInput(e.target.value)}
                        placeholder="Username"
                        className="w-full px-3 py-1.5 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                      />
                    </div>
                    <div className="col-span-4">
                      <label className="block text-[11px] text-slate-400 mb-1">Duration (s)</label>
                      <input
                        type="number"
                        value={micDurationInput}
                        onChange={(e) => setMicDurationInput(e.target.value)}
                        placeholder="Sec"
                        className="w-full px-3 py-1.5 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 tabular-nums"
                      />
                    </div>
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400 mb-1">
                      Captured Audio Transcript (Stored for !who is &amp; !info on)
                    </label>
                    <input
                      type="text"
                      value={micTranscriptInput}
                      onChange={(e) => setMicTranscriptInput(e.target.value)}
                      placeholder="Spoken words on microphone..."
                      className="w-full px-3 py-1.5 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100"
                    />
                  </div>
                  <button
                    type="submit"
                    className="w-full px-3 py-2 text-xs font-medium bg-emerald-400 text-slate-950 rounded-lg hover:bg-emerald-300 transition-colors whitespace-nowrap"
                  >
                    Store Mic Grab + Audio Transcript
                  </button>
                </form>

                {/* Hold-to-Talk Button(50000) [l=1291,t=1169,r=1361,b=1195] */}
                <div className="pt-3 border-t border-slate-800 space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-300 font-medium">Talk Button(50000) Hold-Press</span>
                    <span className="font-mono text-slate-400">[1291, 1169, 1361, 1195]</span>
                  </div>
                  <button
                    type="button"
                    onMouseDown={() => {
                      setIsHoldingTalk(true);
                      holdStartRef.current = Date.now();
                    }}
                    onMouseUp={() => {
                      if (isHoldingTalk) {
                        setIsHoldingTalk(false);
                        const heldSec = Math.max(1, Math.round((Date.now() - holdStartRef.current) / 1000));
                        engine.store.recordMicGrab(
                          BOT_USERNAME,
                          heldSec,
                          undefined,
                          `2 quick clicks + hold on Button(50000) [1291,1169,1361,1195] (${BOT_USERNAME} persisted ${MIC_CONFIRM_PERSIST_SECONDS}s at [1506,1174,1548,1190])`,
                          selectedRoom,
                          true
                        );
                        bump();
                      }
                    }}
                    onMouseLeave={() => {
                      if (isHoldingTalk) setIsHoldingTalk(false);
                    }}
                    className={`w-full py-2.5 px-4 text-xs font-mono rounded-lg border transition-colors flex items-center justify-center gap-2 whitespace-nowrap ${
                      isHoldingTalk
                        ? 'bg-emerald-400 text-slate-950 border-emerald-300 font-semibold'
                        : 'bg-slate-950 hover:bg-slate-800 text-slate-200 border-slate-800'
                    }`}
                  >
                    <Radio className="w-4 h-4" />
                    {isHoldingTalk
                      ? 'BROADCASTING ON TALK BUTTON [1291,1169,1361,1195]...'
                      : 'Hold Press to Broadcast Audio (Talk Button)'}
                  </button>
                </div>
              </div>

              {/* Bot Runtime Settings */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">03. Bot Runtime Switches</h2>
                <div className="divide-y divide-slate-800 text-sm">
                  <div className="py-3 flex items-center justify-between">
                    <div>
                      <div className="font-medium text-slate-200">Continuous Audio Store (!transcribe)</div>
                      <div className="text-xs text-slate-400">Index mic speech into user profiles &amp; word stats</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        engine.settings.continuous_audio_store = !engine.settings.continuous_audio_store;
                        engine.settings.transcription_mode = engine.settings.continuous_audio_store;
                        bump();
                      }}
                      className={`px-3 py-1.5 text-xs font-mono rounded-md border whitespace-nowrap ${
                        engine.settings.continuous_audio_store
                          ? 'bg-emerald-500/20 border-emerald-500/50 text-emerald-200'
                          : 'bg-slate-950 border-slate-800 text-slate-400'
                      }`}
                    >
                      {engine.settings.continuous_audio_store ? 'RECORDING' : 'OFF'}
                    </button>
                  </div>

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
                      <div className="text-xs text-slate-400">Keep recording UIA &amp; audio without replying</div>
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
                </div>
              </div>

              {/* Strict Moderation Notice Parser */}
              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">04. Moderation Notice Parser</h2>
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
                        REJECTED: Treated as regular chat prose
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
            </div>
          </div>
        )}

        {/* SECTION 2: SQLITE DATABASE, AUDIO TRANSCRIPTS & SUPPRESSION VAULT */}
        {activeSection === 'database' && (
          <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
              <div>
                <h2 className="text-lg font-semibold text-white">
                  SQLite Persistence, Stored Audio Transcripts &amp; Suppression Vault
                </h2>
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
                    { id: 'transcripts', label: `audio_transcripts (${transcriptsList.length})` },
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
                      <th className="py-2.5 px-3">joined_at</th>
                      <th className="py-2.5 px-3 text-right">chat_duration</th>
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
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{u.joined_at || '—'}</td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 tabular-nums">
                          {Math.round(u.total_chat_seconds || 0)}s
                        </td>
                        <td className="py-2.5 px-3 text-right text-slate-200 tabular-nums">{u.message_count}</td>
                        <td className="py-2.5 px-3 text-right text-slate-300 tabular-nums">
                          {u.active === 1 ? '1 (In Room)' : '0 (Quit)'}
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
                        <th className="py-2.5 px-3">source</th>
                        <th className="py-2.5 px-3">body</th>
                        <th className="py-2.5 px-3">room_time</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                      {filteredMessages.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-900/60">
                          <td className="py-2.5 px-3 text-slate-400 tabular-nums">{m.id}</td>
                          <td className="py-2.5 px-3 font-semibold text-white">{m.username}</td>
                          <td className="py-2.5 px-3 text-slate-400">{m.source || 'chat'}</td>
                          <td className="py-2.5 px-3 text-slate-200">{m.body}</td>
                          <td className="py-2.5 px-3 text-slate-400 tabular-nums">{m.room_time}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {dbTab === 'transcripts' && (
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-slate-800 text-xs text-slate-400 font-mono">
                      <th className="py-2.5 px-3">id</th>
                      <th className="py-2.5 px-3">speaker</th>
                      <th className="py-2.5 px-3">transcript</th>
                      <th className="py-2.5 px-3 text-right">duration_seconds</th>
                      <th className="py-2.5 px-3">room</th>
                      <th className="py-2.5 px-3">observed_at</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {transcriptsList.map((tr) => (
                      <tr key={tr.id} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{tr.id}</td>
                        <td className="py-2.5 px-3 text-sky-300 font-semibold">{tr.speaker}</td>
                        <td className="py-2.5 px-3 text-slate-100">{tr.transcript}</td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 tabular-nums">
                          {tr.duration_seconds}s
                        </td>
                        <td className="py-2.5 px-3 text-slate-400">{tr.room}</td>
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{tr.observed_at}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
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
                      <th className="py-2.5 px-3">stored_transcript</th>
                      <th className="py-2.5 px-3">started_at</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                    {micGrabsList.map((g) => (
                      <tr key={g.id} className="hover:bg-slate-900/60">
                        <td className="py-2.5 px-3 text-slate-400 tabular-nums">{g.id}</td>
                        <td className="py-2.5 px-3 text-white font-semibold">{g.username}</td>
                        <td className="py-2.5 px-3 text-right text-emerald-300 tabular-nums">{g.duration_seconds}s</td>
                        <td className="py-2.5 px-3 text-slate-300">{g.transcript || '—'}</td>
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
                    user to move their chat, mic grabs, and audio transcripts into{' '}
                    <code className="text-slate-200">data/suppressed/</code>.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-950">
                    {suppressedList.map((vault) => (
                      <div key={vault.username} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1 font-mono text-xs">
                          <div className="text-amber-300 font-semibold">{vault.username} (Suppressed)</div>
                          <div className="text-slate-400">
                            Vault Path: {vault.vault_file} · Suppressed At: {vault.suppressed_at} · Messages:{' '}
                            {vault.messages.length} · Grabs: {vault.mic_grabs.length} · Audio Transcripts:{' '}
                            {vault.audio_transcripts?.length || 0}
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

        {/* SECTION 3: CALIBRATED UIA CONTROL RECTANGLES & IGNORED LISTITEMS */}
        {activeSection === 'uia' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-8 border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-lg font-semibold text-white">
                  Calibrated UIA Control Tree &amp; Trending [l=2359, r=2559] User List Filter
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Pulls chat &amp; moderation from <code className="text-slate-200 font-mono">[l=1281,t=170,r=2355,b=1160]</code>,
                  sends text via <code className="text-slate-200 font-mono">Pane(50033) [l=1396,t=1206,r=2497,b=1241]</code>,
                  scans trending <code className="text-slate-200 font-mono">[l=2359,r=2559]</code> items in{' '}
                  <code className="text-slate-200 font-mono">List(50008) [l=2359,t=141,r=2559,b=1160]</code> while removing{' '}
                  <code className="text-amber-300 font-mono">YOU ARE VIEWING #</code> and{' '}
                  <code className="text-amber-300 font-mono">LURKERS #</code>, and watches{' '}
                  <code className="text-slate-200 font-mono">Button(50000) [l=1506,t=1174,r=1548,b=1190]</code> for{' '}
                  <code className="text-emerald-300 font-mono">{BOT_USERNAME}</code> ({MIC_CONFIRM_PERSIST_SECONDS}s).
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2.5 px-3">ControlType</th>
                      <th className="py-2.5 px-3">Name / Element</th>
                      <th className="py-2.5 px-3 text-right">BoundingRectangle [l, t, r, b]</th>
                      <th className="py-2.5 px-3 text-right">Roster Extraction Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {uiaNodes.map((n) => {
                      const rectTuple: [number, number, number, number] = [n.left, n.top, n.right, n.bottom];
                      const cleaned = cleanUsername(n.name, rectTuple);
                      return (
                        <tr key={n.id} className="hover:bg-slate-900/60">
                          <td className="py-2.5 px-3 text-emerald-300">{n.control_type}</td>
                          <td className="py-2.5 px-3 text-white">{n.name}</td>
                          <td className="py-2.5 px-3 text-right text-slate-300 tabular-nums">
                            [l={n.left}, t={n.top}, r={n.right}, b={n.bottom}]
                          </td>
                          <td className="py-2.5 px-3 text-right">
                            {n.ignored_reason ? (
                              <span className="text-amber-300">{n.ignored_reason}</span>
                            ) : cleaned && n.control_type === 'ListItem(50007)' ? (
                              <span className="text-emerald-300">Valid User: {cleaned} (r=2559)</span>
                            ) : (
                              <span className="text-slate-500">Structural Control</span>
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
                <h2 className="text-lg font-semibold text-white">Calibrated BoundingRectangles</h2>
                <p className="text-xs text-slate-400">
                  Exact coordinates independent of room topic changes in the window title:
                </p>
                <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 overflow-x-auto">
                  {JSON.stringify(
                    {
                      tabs: {
                        Room_List: '(1390, 50)',
                        Players__Lounge: '(1550, 50)',
                      },
                      chat_window_Pane_50033: '[l=1281, t=170, r=2355, b=1160]',
                      chat_window_Text_50020: '[l=1281, t=170, r=2355, b=1160]',
                      chat_input_Pane_50033: '[l=1396, t=1206, r=2497, b=1241]',
                      user_list_List_50008: '[l=2359, t=141, r=2559, b=1160]',
                      user_list_trend_span: '[l=2359, r=2559] (max 100 users)',
                      filtered_headers: ['YOU ARE VIEWING #', 'VIEWING #', 'LURKERS #'],
                      talk_button_Button_50000: '[l=1291, t=1169, r=1361, b=1195]',
                      active_speaker_Button_50000: '[l=1506, t=1174, r=1548, b=1190]',
                      bot_broadcast_gate: `${BOT_USERNAME} persists ${MIC_CONFIRM_PERSIST_SECONDS}s`,
                      top_gifters_Text_50020: '[l=1281, t=71, r=2559, b=1160]',
                    },
                    null,
                    2
                  )}
                </pre>
              </div>

              <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <h2 className="text-lg font-semibold text-white">MODERATION_ALLOWED_SENDERS</h2>
                <p className="text-xs text-slate-400">
                  Trusted operators authorized to emit slash commands:
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

        {/* SECTION 4: FIXED ROOM TAB COORDINATES */}
        {activeSection === 'rooms' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <div className="lg:col-span-7 border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-5">
              <div className="border-b border-slate-800 pb-4">
                <h2 className="text-lg font-semibold text-white">
                  Fixed Tab Coordinates (Independent of Dynamic Window Title/Topic)
                </h2>
                <p className="text-xs text-slate-400 mt-1">
                  Since the Camfrog window title changes whenever the room topic changes, tab identification uses the
                  fixed screen coordinates <code className="text-slate-200">(1390, 50)</code> and{' '}
                  <code className="text-slate-200">(1550, 50)</code>.
                </p>
              </div>

              <div className="divide-y divide-slate-800 border border-slate-800 rounded-lg bg-slate-950">
                {(Object.entries(ROOM_TAB_POSITIONS) as Array<[RoomName, [number, number, number, number]]>).map(
                  ([roomName, [left, top, right, bottom]]) => {
                    const isCurrent = engine.currentRoom === roomName;
                    const [clickX, clickY] = ROOM_TAB_CLICK_POINTS[roomName];
                    return (
                      <div key={roomName} className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-mono font-semibold text-white">{roomName}</span>
                            <span aria-hidden="true" className="text-slate-500">
                              ·
                            </span>
                            <span className="text-xs font-mono text-emerald-300 tabular-nums">
                              Calibrated Point: ({clickX}, {clickY})
                            </span>
                          </div>
                          <div className="text-xs text-slate-400 font-mono tabular-nums">
                            Tab BoundingRectangle: [l={left}, t={top}, r={right}, b={bottom}]
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
                          {isCurrent ? `Active @ (${clickX}, ${clickY})` : `Click (${clickX}, ${clickY})`}
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
                    <label className="block text-xs text-slate-400 mb-1">X Coordinate (e.g. 1390 or 1550)</label>
                    <input
                      type="number"
                      value={probeX}
                      onChange={(e) => setProbeX(e.target.value)}
                      className="w-full px-3 py-2 text-xs font-mono bg-slate-950 border border-slate-800 rounded-lg text-slate-100 tabular-nums"
                    />
                  </div>
                  <div>
                    <label className="block text-xs text-slate-400 mb-1">Y Coordinate (e.g. 50)</label>
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
                All triggers defined in <code className="text-slate-200">TRIGGER_NAMES</code>:
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
                  Executes the unit tests against <code className="text-slate-200">CamfrogBotEngine</code>,{' '}
                  <code className="text-slate-200">CamfrogStore</code>, and the ignored{' '}
                  <code className="text-slate-200">ListItem(50007)</code> coordinate filters.
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

        {/* SECTION 6: FIXED LOCAL PYTHON FILES FOR C:\Users\newbe\AIBot */}
        {activeSection === 'python_fix' && (
          <div className="space-y-6">
            <div className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                <div>
                  <h2 className="text-lg font-semibold text-white">
                    Synchronized Python Pipeline Files for <code className="font-mono text-emerald-300">C:\Users\newbe\AIBot</code>
                  </h2>
                  <p className="text-xs text-slate-300 leading-relaxed mt-1">
                    All 6 Python files below are 100% synchronized with your new Camfrog UIA coordinates: Chat Window <code className="text-slate-100">[1281,170,2355,1160]</code>, Compound <code className="text-slate-100">DataItem(50029)</code> <code className="text-slate-100">Join:/Quit:</code> rows at <code className="text-slate-100">[1332..2330]</code>, Chat Input <code className="text-slate-100">[1396,1206,2497,1241]</code>, User List <code className="text-slate-100">[2359,141,2559,1160]</code> (<code className="text-slate-100">Users (#)</code> / <code className="text-slate-100">MEMBERS # + LURKERS #</code> / row count minus 3 headers), Talk Button <code className="text-slate-100">[1291,1169,1361,1195]</code>, and Active Speaker <code className="text-slate-100">[1506,1174,1548,1190]</code> (<code className="text-slate-100">{BOT_USERNAME}</code> {MIC_CONFIRM_PERSIST_SECONDS}s gate).
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2 self-start">
                  <button
                    type="button"
                    onClick={() => {
                      const allFiles = [
                        { name: 'config.py', code: FIXED_CONFIG_PY },
                        { name: 'ui_automation.py', code: FIXED_UI_AUTOMATION_PY },
                        { name: 'camfrog_bot.py', code: FIXED_CAMFROG_BOT_PY },
                        { name: 'room_monitor.py', code: FIXED_ROOM_MONITOR_PY },
                        { name: 'room_data_processor.py', code: FIXED_ROOM_DATA_PROCESSOR_PY },
                        { name: 'test_bot.py', code: FIXED_TEST_BOT_PY },
                      ];
                      const psLines = [
                        '# One-Click Clean & Install Script for C:\\Users\\newbe\\AIBot',
                        '$targetDir = "C:\\Users\\newbe\\AIBot"',
                        'New-Item -ItemType Directory -Force -Path $targetDir | Out-Null',
                        'Set-Location $targetDir',
                        'Write-Host "Cleaning old cache, legacy scripts, and stale database..." -ForegroundColor Cyan',
                        'Remove-Item -Path "__pycache__" -Recurse -Force -ErrorAction SilentlyContinue',
                        'Remove-Item -Path "camfrog_boy.py", "bot.py", "monitor_bot.py", "setup_bot.py", "start_bot_test.py", "test_camfrog_connection.py", "get_camfrog_window.py" -Force -ErrorAction SilentlyContinue',
                        'Remove-Item -Path "data\\camfrog_bot.db" -Force -ErrorAction SilentlyContinue',
                      ];
                      for (const f of allFiles) {
                        const b64 = window.btoa(unescape(encodeURIComponent(f.code)));
                        psLines.push(
                          `[System.IO.File]::WriteAllText((Join-Path $targetDir "${f.name}"), [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String("${b64}")))`
                        );
                        psLines.push(`Write-Host "Wrote ${f.name}" -ForegroundColor Green`);
                      }
                      psLines.push('Write-Host "`nRunning unit tests (python test_bot.py)..." -ForegroundColor Cyan');
                      psLines.push('python test_bot.py');
                      psLines.push('Write-Host "`nAll 6 clean pipeline files are installed in C:\\Users\\newbe\\AIBot!" -ForegroundColor Green');
                      handleDownloadPython('clean_and_install_aibot.ps1', psLines.join('\r\n'));
                    }}
                    className="px-4 py-2 text-xs font-mono bg-emerald-400 text-slate-950 font-semibold rounded-lg hover:bg-emerald-300 flex items-center gap-2 whitespace-nowrap"
                  >
                    <Download className="w-4 h-4" />
                    Download 1-Click Clean &amp; Install (.ps1)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      const allFiles = [
                        { name: 'config.py', code: FIXED_CONFIG_PY },
                        { name: 'ui_automation.py', code: FIXED_UI_AUTOMATION_PY },
                        { name: 'camfrog_bot.py', code: FIXED_CAMFROG_BOT_PY },
                        { name: 'room_monitor.py', code: FIXED_ROOM_MONITOR_PY },
                        { name: 'room_data_processor.py', code: FIXED_ROOM_DATA_PROCESSOR_PY },
                        { name: 'test_bot.py', code: FIXED_TEST_BOT_PY },
                      ];
                      allFiles.forEach((f, idx) => {
                        setTimeout(() => handleDownloadPython(f.name, f.code), idx * 220);
                      });
                    }}
                    className="px-4 py-2 text-xs font-mono bg-slate-800 hover:bg-slate-700 text-white border border-slate-700 font-semibold rounded-lg flex items-center gap-2 whitespace-nowrap"
                  >
                    <Download className="w-4 h-4" />
                    Download All 6 .py Files
                  </button>
                </div>
              </div>

              {/* Direct Individual Download Strip */}
              <div className="pt-2 border-t border-slate-800">
                <div className="text-xs font-semibold text-slate-300 mb-2">
                  Individual Python Files (Click any file to download directly into <code className="text-emerald-300">C:\Users\newbe\AIBot</code>):
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                  {[
                    { name: 'config.py', desc: 'Calibrated coordinates & settings', code: FIXED_CONFIG_PY },
                    { name: 'ui_automation.py', desc: 'UIA + OCR + DataItem(50029) + Users (#)', code: FIXED_UI_AUTOMATION_PY },
                    { name: 'camfrog_bot.py', desc: 'Main bot + SQLite duration + TTS', code: FIXED_CAMFROG_BOT_PY },
                    { name: 'room_monitor.py', desc: 'Live second-terminal room monitor', code: FIXED_ROOM_MONITOR_PY },
                    { name: 'room_data_processor.py', desc: 'Multi-room trigger processor', code: FIXED_ROOM_DATA_PROCESSOR_PY },
                    { name: 'test_bot.py', desc: '9 offline unit tests', code: FIXED_TEST_BOT_PY },
                  ].map((item) => (
                    <div
                      key={item.name}
                      className="flex items-center justify-between p-3 rounded-lg bg-slate-950 border border-slate-800"
                    >
                      <div className="min-w-0 pr-2">
                        <div className="font-mono text-xs font-semibold text-white truncate">{item.name}</div>
                        <div className="text-[11px] text-slate-400 truncate">{item.desc}</div>
                      </div>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          type="button"
                          onClick={() => handleCopyPython(item.name, item.code)}
                          className="px-2.5 py-1 text-xs font-mono bg-slate-900 hover:bg-slate-800 text-slate-200 border border-slate-700 rounded flex items-center gap-1"
                        >
                          {copiedFile === item.name ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                          {copiedFile === item.name ? 'Copied' : 'Copy'}
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDownloadPython(item.name, item.code)}
                          className="px-2.5 py-1 text-xs font-mono bg-emerald-400 text-slate-950 font-semibold rounded hover:bg-emerald-300 flex items-center gap-1"
                        >
                          <Download className="w-3 h-3" />
                          .py
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-300 space-y-1.5">
                <div className="text-emerald-300 font-semibold">Clean Local Folder Checklist (C:\Users\newbe\AIBot):</div>
                <div>
                  1. Clean old pipeline files in Command Prompt:{' '}
                  <code className="text-rose-300">
                    rmdir /s /q __pycache__ &amp;&amp; del /q data\camfrog_bot.db camfrog_boy.py bot.py monitor_bot.py
                  </code>
                </div>
                <div>
                  2. Save the 6 downloaded <code className="text-white">.py</code> files directly into <code className="text-white">C:\Users\newbe\AIBot</code> (Make sure Windows didn&apos;t rename them <code className="text-amber-300">ui_automation (1).py</code> in your Downloads folder!).
                </div>
                <div>3. Verify all 9 unit tests pass: <code className="text-emerald-300">python test_bot.py</code></div>
                <div>4. Start live room monitor: <code className="text-emerald-300">python room_monitor.py</code> (and main bot: <code className="text-emerald-300">python camfrog_bot.py</code>)</div>
              </div>
            </div>

            {[
              { name: 'config.py', code: FIXED_CONFIG_PY },
              { name: 'ui_automation.py', code: FIXED_UI_AUTOMATION_PY },
              { name: 'camfrog_bot.py', code: FIXED_CAMFROG_BOT_PY },
              { name: 'room_monitor.py', code: FIXED_ROOM_MONITOR_PY },
              { name: 'room_data_processor.py', code: FIXED_ROOM_DATA_PROCESSOR_PY },
              { name: 'test_bot.py', code: FIXED_TEST_BOT_PY },
            ].map((file) => (
              <div key={file.name} className="border border-slate-800 rounded-xl bg-slate-900/50 p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="font-mono text-sm font-semibold text-white">{file.name}</span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleCopyPython(file.name, file.code)}
                      className="px-3 py-1.5 text-xs font-mono bg-slate-950 hover:bg-slate-800 text-slate-200 border border-slate-800 rounded-md flex items-center gap-1.5 whitespace-nowrap"
                    >
                      {copiedFile === file.name ? (
                        <>
                          <Check className="w-3.5 h-3.5 text-emerald-400" />
                          Copied!
                        </>
                      ) : (
                        <>
                          <Copy className="w-3.5 h-3.5" />
                          Copy {file.name}
                        </>
                      )}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDownloadPython(file.name, file.code)}
                      className="px-3 py-1.5 text-xs font-mono bg-emerald-400 text-slate-950 font-semibold rounded-md hover:bg-emerald-300 flex items-center gap-1.5 whitespace-nowrap"
                    >
                      <Download className="w-3.5 h-3.5" />
                      Download {file.name}
                    </button>
                  </div>
                </div>
                <pre className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono text-slate-200 max-h-[420px] overflow-auto">
                  {file.code}
                </pre>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;
