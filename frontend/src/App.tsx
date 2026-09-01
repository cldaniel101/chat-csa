import "./App.css";
import { CSAChatWidget } from "./components/chat/CSAChatWidget";
import { useEffect } from "react";

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

  useEffect(() => {
    document.documentElement.classList.toggle("csa-embed-mode", embedded);
    return () => {
      document.documentElement.classList.remove("csa-embed-mode");
    };
  }, [embedded]);

  return (
    <div className={`app${embedded ? " app--embedded" : ""}`}>
      <main className="main">
        {!embedded && (
          /* Mock: captura (full-page) do portal real da CSA como fundo,
             para simular o botão do chat embutido na página do portal. */
          <img
            className="csa-page-backdrop"
            src="/csa-portal.png"
            alt=""
            aria-hidden="true"
            draggable={false}
          />
        )}
        <CSAChatWidget embedded={embedded} />
      </main>
    </div>
  );
}
