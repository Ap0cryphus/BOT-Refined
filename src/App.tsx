import React, { useState } from "react";
import { TopBar } from "./components/TopBar";
import { CloneStatusRibbon } from "./components/CloneStatusRibbon";
import { PixelMethodBar } from "./components/PixelMethodBar";
import { HeroBanner } from "./components/HeroBanner";
import { HudBar } from "./components/HudBar";
import { TriggerDecks } from "./components/TriggerDecks";
import { SplitTerminals } from "./components/SplitTerminals";
import { InputLines } from "./components/InputLines";
import { SetupWizardModal } from "./components/SetupWizardModal";
import { DiagnosticsModal } from "./components/DiagnosticsModal";
import { UserDatabaseModal } from "./components/UserDatabaseModal";
import { SpinAnalyticsModal } from "./components/SpinAnalyticsModal";
import { HeistSimulatorModal } from "./components/HeistSimulatorModal";

export const App: React.FC = () => {
  const [wizardOpen, setWizardOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [usersOpen, setUsersOpen] = useState(false);
  const [analyticsOpen, setAnalyticsOpen] = useState(false);
  const [heistOpen, setHeistOpen] = useState(false);

  return (
    <div className="relative min-h-screen bg-[#060A12] text-[#F8FAFC] flex flex-col p-2 md:p-3 space-y-2 max-w-[1720px] mx-auto select-none overflow-x-hidden">
      {/* Top Action Bar */}
      <TopBar
        onOpenWizard={() => setWizardOpen(true)}
        onOpenDiagnostics={() => setDiagnosticsOpen(true)}
      />

      {/* Dedicated Clone Mode Live Status & Audio Hijack Ribbon */}
      <CloneStatusRibbon />

      {/* Method 2 Direct Pixel Coordinate Calibration Bar */}
      <PixelMethodBar />

      {/* Hero Banner Showcase with KaeKae & PepeFrog Artwork */}
      <HeroBanner
        onOpenUsers={() => setUsersOpen(true)}
        onOpenAnalytics={() => setAnalyticsOpen(true)}
        onOpenHeist={() => setHeistOpen(true)}
      />

      {/* HUD Telemetry + Dynamic Active Speaker & PAT Bar */}
      <HudBar />

      {/* Interactive Trigger Button Decks */}
      <TriggerDecks />

      {/* Three Vertically-Stacked Split Terminals */}
      <SplitTerminals />

      {/* Three Dedicated Input Lines (Admin CMD, Bot Chat, Mic Line) */}
      <InputLines />

      {/* Interactive Feature Modals */}
      <SetupWizardModal isOpen={wizardOpen} onClose={() => setWizardOpen(false)} />
      <DiagnosticsModal isOpen={diagnosticsOpen} onClose={() => setDiagnosticsOpen(false)} />
      <UserDatabaseModal isOpen={usersOpen} onClose={() => setUsersOpen(false)} />
      <SpinAnalyticsModal isOpen={analyticsOpen} onClose={() => setAnalyticsOpen(false)} />
      <HeistSimulatorModal isOpen={heistOpen} onClose={() => setHeistOpen(false)} />
    </div>
  );
};

export default App;
