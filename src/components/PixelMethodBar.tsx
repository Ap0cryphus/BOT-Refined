import React, { useState, useEffect } from "react";
import { orchestrator } from "../services/botStore";
import { Save, Volume2, MousePointer } from "lucide-react";

export const PixelMethodBar: React.FC = () => {
  const [chatX, setChatX] = useState(orchestrator.calibration.chat_input_screen_pt[0]);
  const [chatY, setChatY] = useState(orchestrator.calibration.chat_input_screen_pt[1]);
  const [talkX, setTalkX] = useState(orchestrator.calibration.talk_button_screen_pt[0]);
  const [talkY, setTalkY] = useState(orchestrator.calibration.talk_button_screen_pt[1]);
  const [mouseXY, setMouseXY] = useState<[number, number]>([1536, 1223]);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      // Simulate calibrated screen coordinates scale
      const screenX = Math.round(1273 + (e.clientX / window.innerWidth) * (2567 - 1273));
      const screenY = Math.round((e.clientY / window.innerHeight) * 1399);
      setMouseXY([screenX, screenY]);
    };
    window.addEventListener("mousemove", handleMouseMove);
    return () => window.removeEventListener("mousemove", handleMouseMove);
  }, []);

  const handleLock = () => {
    orchestrator.setDirectPixels(chatX, chatY, talkX, talkY);
  };

  const handleTestTalk = () => {
    orchestrator.speakOnMic("KaeKae Toad testing calibrated Talk Button pixel coordinate.");
  };

  return (
    <div className="bg-[#0F172A] border border-[#334155] rounded-md px-3 py-1 flex flex-wrap items-center justify-between text-xs font-mono shadow-inner">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-bold text-[#FBBF24]">📌 METHOD 2 (DIRECT PIXELS):</span>

        <div className="flex items-center gap-1 text-[#38BDF8]">
          <span>Chat X:</span>
          <input
            type="number"
            value={chatX}
            onChange={(e) => setChatX(Number(e.target.value))}
            className="w-14 bg-[#030712] border border-[#38BDF8]/40 px-1 py-0.5 rounded text-[#38BDF8] text-center font-bold"
          />
          <span>Y:</span>
          <input
            type="number"
            value={chatY}
            onChange={(e) => setChatY(Number(e.target.value))}
            className="w-14 bg-[#030712] border border-[#38BDF8]/40 px-1 py-0.5 rounded text-[#38BDF8] text-center font-bold"
          />
        </div>

        <div className="flex items-center gap-1 text-[#34D399] ml-2">
          <span>Talk Btn X:</span>
          <input
            type="number"
            value={talkX}
            onChange={(e) => setTalkX(Number(e.target.value))}
            className="w-14 bg-[#030712] border border-[#34D399]/40 px-1 py-0.5 rounded text-[#34D399] text-center font-bold"
          />
          <span>Y:</span>
          <input
            type="number"
            value={talkY}
            onChange={(e) => setTalkY(Number(e.target.value))}
            className="w-14 bg-[#030712] border border-[#34D399]/40 px-1 py-0.5 rounded text-[#34D399] text-center font-bold"
          />
        </div>

        <button
          onClick={handleLock}
          className="flex items-center gap-1 px-2.5 py-0.5 text-xs font-bold rounded bg-[#0284C7] hover:bg-[#38BDF8] text-white transition-all cursor-pointer shadow-sm ml-1"
        >
          <Save className="w-3 h-3" />
          <span>💾 LOCK PIXELS</span>
        </button>

        <button
          onClick={handleTestTalk}
          className="flex items-center gap-1 px-2.5 py-0.5 text-xs font-bold rounded bg-[#059669] hover:bg-[#10B981] text-white transition-all cursor-pointer shadow-sm"
        >
          <Volume2 className="w-3 h-3" />
          <span>🎙️ TEST TALK BTN</span>
        </button>
      </div>

      <div className="flex items-center gap-1 text-[#E2E8F0] font-bold">
        <MousePointer className="w-3.5 h-3.5 text-amber-400" />
        <span>Live Mouse XY: ({mouseXY[0]}, {mouseXY[1]})</span>
      </div>
    </div>
  );
};
