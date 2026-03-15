function SessionControls({
  sessionState,
  startSession,
  endSession,
}) {
  if (sessionState === 'connecting') {
    return (
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-2 text-gray-600">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Connecting...
        </div>
        <button
          type="button"
          disabled
          className="rounded-lg bg-gray-300 px-6 py-3 font-medium text-gray-500 cursor-not-allowed"
        >
          Connecting...
        </button>
      </div>
    );
  }

  if (sessionState === 'ending') {
    return (
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-2 text-gray-600">
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
          Ending session...
        </div>
        <button
          type="button"
          disabled
          className="rounded-lg bg-gray-300 px-6 py-3 font-medium text-gray-500 cursor-not-allowed"
        >
          Ending session...
        </button>
      </div>
    );
  }

  if (sessionState === 'active') {
    return (
      <div className="flex flex-col items-center gap-3">
        <p className="text-sm text-gray-600">Use headphones for the best experience. Speaker audio may cause echo.</p>
        <p className="text-sm text-gray-600">Speak to ask questions — CodeWhisper hears you.</p>
        <p className="text-xs text-gray-500">A small control panel opened — keep it beside your IDE to change mode without switching back.</p>
        <button
          type="button"
          onClick={endSession}
          className="rounded-lg border-2 border-red-300 bg-white px-5 py-2.5 font-medium text-red-700 hover:bg-red-50"
        >
          End Session
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-4">
      <button
        type="button"
        onClick={startSession}
        className="rounded-lg bg-indigo-600 px-8 py-4 font-semibold text-white hover:bg-indigo-700"
      >
        Start Session
      </button>
      <p className="max-w-sm text-center text-sm text-gray-500">
        You’ll be asked to share your screen and mic. To share your IDE (VS Code, Cursor), choose
        <strong> Entire Screen</strong> or pick your IDE window.
      </p>
    </div>
  );
}

export default SessionControls;
