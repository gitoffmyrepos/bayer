export function LoadingState({ label = "Preparing your next mission" }: { label?: string }) {
  return (
    <div className="state-panel" role="status">
      <span className="loader" aria-hidden="true" />
      <p>{label}</p>
    </div>
  );
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return (
    <div className="state-panel state-panel--error" role="alert">
      <p>{message}</p>
      {retry && <button onClick={retry}>Try again</button>}
    </div>
  );
}
