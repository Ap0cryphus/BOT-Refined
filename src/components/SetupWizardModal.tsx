import React, { useState } from "react";
import { orchestrator } from "../services/botStore";
import { X, CheckCircle, Sliders, Volume2, Monitor, Cpu } from "lucide-react";

interface SetupWizardModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const SetupWizardModal: React.FC<SetupWizardModalProps> = ({ isOpen, onClose }) => {
  const [step, setStep] = useState(1);
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 font-mono">
      <div className="bg-[#0B1120] border border-[#38BDF8] rounded-lg max-w-2xl w-full p-5 shadow-2xl space-y-4 text-xs text-slate-200">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-700 pb-2.5">
          <div className="flex items-center gap-2">
            <Sliders className="w-5 h-5 text-sky-400" />
            <h2 className="text-base font-bold text-white">Camfrog & PepeFrog Setup Wizard</h2>
          </div>
          <button onClick={onClose} className="p-1 rounded text-slate-400 hover:text-white cursor-pointer">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Stepper */}
        <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
          <div className={`p-2 rounded border ${step === 1 ? "bg-sky-950/60 border-sky-400 text-sky-300 font-bold" : "bg-slate-900 border-slate-800 text-slate-400"}`}>
            1. Window & UIA Calibration
          </div>
          <div className={`p-2 rounded border ${step === 2 ? "bg-sky-950/60 border-sky-400 text-sky-300 font-bold" : "bg-slate-900 border-slate-800 text-slate-400"}`}>
            2. Audio & VB-Cable Loopback
          </div>
          <div className={`p-2 rounded border ${step === 3 ? "bg-sky-950/60 border-sky-400 text-sky-300 font-bold" : "bg-slate-900 border-slate-800 text-slate-400"}`}>
            3. DirectML GPU & AI Models
          </div>
        </div>

        {/* Content */}
        <div className="p-3 bg-[#050811] rounded border border-slate-800 space-y-3 min-h-[180px]">
          {step === 1 && (
            <div className="space-y-2">
              <h3 className="font-bold text-amber-300 flex items-center gap-1.5">
                <Monitor className="w-4 h-4" />
                Step 1: Camfrog Client Window & Text Box Calibration
              </h3>
              <p className="text-slate-300 text-[11px]">
                The orchestrator attaches to the <strong>Players__Lounge</strong> window and calculates click points:
              </p>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800 space-y-1 text-[11px]">
                <div>• Main Window: <code className="text-sky-300">[{orchestrator.calibration.window_rect.join(", ")}]</code></div>
                <div>• Chat Text Field: <code className="text-amber-300">[{orchestrator.calibration.chat_input_rect.join(", ")}]</code> &rarr; Point: <strong>({orchestrator.calibration.chat_input_screen_pt.join(", ")})</strong></div>
                <div>• Talk Button: <code className="text-emerald-300">[{orchestrator.calibration.talk_button_rect.join(", ")}]</code> &rarr; Point: <strong>({orchestrator.calibration.talk_button_screen_pt.join(", ")})</strong></div>
                <div>• Last Calibrated: <em>{orchestrator.calibration.calibrated_at}</em></div>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-2">
              <h3 className="font-bold text-emerald-300 flex items-center gap-1.5">
                <Volume2 className="w-4 h-4" />
                Step 2: VB-Cable & Microphone Persistence Gate
              </h3>
              <p className="text-slate-300 text-[11px]">
                Audio is routed through virtual audio cable to Camfrog without feedback:
              </p>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800 space-y-1 text-[11px]">
                <div>• Virtual Audio Cable: <span className="text-emerald-400 font-bold">CABLE Input (VB-Audio Virtual Cable)</span></div>
                <div>• Talk Button Sequence: <span className="text-slate-200">3 fast clicks (~33ms) + 4th held click</span></div>
                <div>• Speaker Persistence Gate: <span className="text-slate-200">Holds mic until "KaeKae_Toad" persists &gt;= 1.3s</span></div>
                <div>• Speech Engine: <span className="text-sky-400">WhisperX base.en FP16 + Edge/Kokoro/XTTS</span></div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-2">
              <h3 className="font-bold text-purple-300 flex items-center gap-1.5">
                <Cpu className="w-4 h-4" />
                Step 3: DirectML Hardware Acceleration & Voice Cloning
              </h3>
              <p className="text-slate-300 text-[11px]">
                Dedicated GPU stack verified for real-time transcription and instant voice generation:
              </p>
              <div className="bg-slate-900 p-2.5 rounded border border-slate-800 space-y-1 text-[11px]">
                <div>• Discrete GPU: <span className="text-purple-300 font-bold">AMD Radeon RX 9070 XT (16GB VRAM)</span></div>
                <div>• Backend: <span className="text-emerald-400">DirectML DirectX 12 Native Execution</span></div>
                <div>• Kokoro-82M ONNX: <span className="text-emerald-400 font-bold">Loaded (data/models/kokoro/.ready)</span></div>
                <div>• Coqui XTTS-v2: <span className="text-emerald-400 font-bold">Loaded (data/models/xtts_v2/.ready)</span></div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between pt-2 border-t border-slate-800">
          <div>
            {step > 1 && (
              <button
                onClick={() => setStep(step - 1)}
                className="px-3 py-1 rounded bg-slate-800 hover:bg-slate-700 text-white font-bold cursor-pointer"
              >
                Back
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            {step < 3 ? (
              <button
                onClick={() => setStep(step + 1)}
                className="px-4 py-1 rounded bg-[#0284C7] hover:bg-[#38BDF8] text-white font-bold cursor-pointer"
              >
                Next &rarr;
              </button>
            ) : (
              <button
                onClick={onClose}
                className="px-4 py-1 rounded bg-[#10B981] hover:bg-[#34D399] text-[#022C22] font-bold cursor-pointer flex items-center gap-1"
              >
                <CheckCircle className="w-4 h-4" />
                <span>Finish & Close</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
