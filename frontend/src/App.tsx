import "./App.css";
import { CSAChatWidget } from "./components/chat/CSAChatWidget";
import { KBExplorer } from "./components/kb/KBExplorer";
import { useEffect, useState } from "react";

function isEmbedMode() {
  if (typeof window === "undefined") {
    return false;
  }

  return new URLSearchParams(window.location.search).has("embed");
}

// Frontend exclusivo do consumer (decisão da discussão ingester-fasthtml-admin):
// o ingester tem painel próprio em FastHTML no backend (/admin).
export default function App() {
  const embedded = isEmbedMode();
  // Controla se o widget de chat está aberto (acionado pelo KBExplorer).
  const [chatOpen, setChatOpen] = useState(false);

  useEffect(() => {
    document.documentElement.classList.toggle("csa-embed-mode", embedded);
    return () => {
      document.documentElement.classList.remove("csa-embed-mode");
    };
  }, [embedded]);

  return (
    <div className={`app${embedded ? " app--embedded" : ""}`}>
      <main className="main">
        {embedded ? (
          /* Modo embed: somente o widget flutuante, sem explorador. */
          <CSAChatWidget embedded={true} />
        ) : (
          <>
            {/* Modo desktop: explorador de arquivos como tela principal. */}
            <KBExplorer onStartChat={() => setChatOpen(true)} />
            {/* Widget do chatbot — controlado pelo explorador. */}
            <CSAChatWidget embedded={false} initialOpen={chatOpen} onOpenChange={setChatOpen} />
          </>
        )}
      </main>
    </div>
  );
}
