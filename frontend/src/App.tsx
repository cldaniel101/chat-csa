import "./App.css";
import { CSAChatWidget } from "./components/chat/CSAChatWidget";

// Frontend exclusivo do consumer (decisão da discussão ingester-fasthtml-admin):
// o ingester tem painel próprio em FastHTML no backend (/admin).
export default function App() {
  return (
    <div className="app">
      <main className="main">
        {/* Mock: captura (full-page) do portal real da CSA como fundo,
            para simular o botão do chat embutido na página do portal. */}
        <img
          className="csa-page-backdrop"
          src="/csa-portal.png"
          alt=""
          aria-hidden="true"
          draggable={false}
        />
        <CSAChatWidget />
      </main>
    </div>
  );
}