import { ArrowUpRight } from "lucide-react";

const CHAT_SUGGESTIONS = [
  "Como funciona a lista de espera?",
  "Quais documentos preciso enviar?",
  "O que significa estar habilitado?",
  "Como acesso o SIDOC?",
] as const;

type ChatSuggestionsProps = {
  disabled?: boolean;
  onSelect: (prompt: string) => void;
};

export function ChatSuggestions({
  disabled = false,
  onSelect,
}: ChatSuggestionsProps) {
  return (
    <div className="csa-chat-suggestions" aria-label="Sugestões de perguntas">
      {CHAT_SUGGESTIONS.map((prompt) => (
        <button
          key={prompt}
          type="button"
          className="csa-chat-suggestion"
          onClick={() => onSelect(prompt)}
          disabled={disabled}
        >
          <span>{prompt}</span>
          <ArrowUpRight size={16} aria-hidden="true" />
        </button>
      ))}
    </div>
  );
}
