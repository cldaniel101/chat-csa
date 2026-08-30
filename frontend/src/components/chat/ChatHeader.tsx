import { MessageCircle, Trash2, X } from "lucide-react";

export type ChatHealth = "ok" | "off" | "checking";

type ChatHeaderProps = {
  health: ChatHealth;
  canClear: boolean;
  onClear: () => void;
  onClose: () => void;
};

const HEALTH_LABEL: Record<ChatHealth, string> = {
  ok: "Assistente disponível",
  off: "Assistente indisponível",
  checking: "Verificando disponibilidade",
};

export function ChatHeader({
  health,
  canClear,
  onClear,
  onClose,
}: ChatHeaderProps) {
  return (
    <header className="csa-chat-header">
      <div className="csa-chat-header-icon" aria-hidden="true">
        <MessageCircle size={22} strokeWidth={2} />
      </div>

      <div className="csa-chat-heading">
        <div className="csa-chat-title-row">
          <h2 id="csa-chat-title">Assistente CSA</h2>
          <span
            className={`csa-chat-health csa-chat-health--${health}`}
            title={HEALTH_LABEL[health]}
          >
            <span className="csa-chat-health-dot" aria-hidden="true" />
            <span className="csa-sr-only">{HEALTH_LABEL[health]}</span>
          </span>
        </div>
        <p>Dúvidas sobre o SiSU UEFS</p>
      </div>

      <div className="csa-chat-header-actions">
        <button
          type="button"
          className="csa-chat-icon-button"
          onClick={onClear}
          disabled={!canClear}
          aria-label="Limpar conversa"
          title="Limpar conversa"
        >
          <Trash2 size={18} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="csa-chat-icon-button"
          onClick={onClose}
          aria-label="Minimizar conversa"
          title="Minimizar conversa"
        >
          <X size={20} aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}
