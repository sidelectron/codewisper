import { useSession } from './hooks/useSession';
import { useHealth } from './hooks/useHealth';
import Header from './components/Header';
import StatusBar from './components/StatusBar';
import SessionControls from './components/SessionControls';
import SessionSummary from './components/SessionSummary';
import LearningPulse from './components/LearningPulse';
import FlowModeIndicator from './components/FlowModeIndicator';
import ControlPanelLauncher from './components/ControlPanelLauncher';

function App() {
  const {
    sessionState,
    startSession,
    endSession,
    startNewSession,
    currentMode,
    switchMode,
    error,
    summary,
    geminiStatus,
    isConnected,
    isRecording,
    isCapturing,
    pulseScore,
  } = useSession();
  const health = useHealth(sessionState === 'active' || sessionState === 'connecting');

  const showSummary = sessionState === 'ended' && summary != null;

  return (
    <div className="min-h-screen flex flex-col bg-white">
      <Header />
      <main className="flex-1 flex flex-col items-center justify-center p-4 pb-24">
        {showSummary ? (
          <SessionSummary summaryText={summary} onStartNewSession={startNewSession} finalPulseScore={pulseScore} />
        ) : (
          <>
            {error && (
              <div
                className="mb-4 w-full max-w-md rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"
                role="alert"
              >
                {error}
              </div>
            )}
            <SessionControls
              sessionState={sessionState}
              startSession={startSession}
              endSession={endSession}
              health={health}
            />
            <div className="mt-4 flex flex-col items-center gap-3 w-full max-w-md">
              <FlowModeIndicator
                currentMode={currentMode}
                onSwitchMode={switchMode}
                sessionState={sessionState}
              />
              <ControlPanelLauncher
                sessionState={sessionState}
                isConnected={isConnected}
                currentMode={currentMode}
                switchMode={switchMode}
                endSession={endSession}
              />
            </div>
          </>
        )}
      </main>
      {!showSummary && (sessionState === 'active' || sessionState === 'connecting') && (
        <LearningPulse score={pulseScore} />
      )}
      {!showSummary && (
        <StatusBar
          isConnected={isConnected}
          sessionState={sessionState}
          geminiStatus={geminiStatus}
          isRecording={isRecording}
          isCapturing={isCapturing}
        />
      )}
    </div>
  );
}

export default App;
