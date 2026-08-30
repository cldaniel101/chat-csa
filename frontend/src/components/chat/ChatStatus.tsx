import { useEffect, useState } from "react";

const STATUS_MESSAGES = [
  "Buscando uma resposta...",
  "Organizando as informações...",
  "Preparando a resposta...",
] as const;

export function ChatStatus() {
  const [statusIndex, setStatusIndex] = useState(0);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setStatusIndex((current) =>
        Math.min(current + 1, STATUS_MESSAGES.length - 1),
      );
    }, 2800);

    return () => window.clearInterval(interval);
  }, []);

  return (
    <div className="csa-chat-message csa-chat-message--assistant csa-chat-status">
      <span className="csa-chat-typing" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span role="status" aria-live="polite">
        {STATUS_MESSAGES[statusIndex]}
      </span>
    </div>
  );
}
