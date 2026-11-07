import { BsStars } from "react-icons/bs";
import { useEffect, useState } from "react";
import "./App.css";
import { CSAChatWidget } from "./components/chat/CSAChatWidget";
import { KBExplorer } from "./components/kb/KBExplorer";

function isEmbedMode() {
  if (typeof window === "undefined") {
    return false;
  }
  return new URLSearchParams(window.location.search).has("embed");
}

function isAdminRoute() {
  if (typeof window === "undefined") {
    return false;
  }
  const path = window.location.pathname.replace(/\/+$/, "") || "/";
  return path === "/admin" || path.startsWith("/admin/");
}

export default function App() {
  const embedded = isEmbedMode();
  const adminRoute = isAdminRoute();
  const [chatOpen, setChatOpen] = useState(!embedded && !adminRoute);

  useEffect(() => {
    document.documentElement.classList.toggle("csa-embed-mode", embedded);
    return () => {
      document.documentElement.classList.remove("csa-embed-mode");
    };
  }, [embedded]);

  if (adminRoute) {
    return (
      <div className="app app--admin">
        <main className="main">
          <KBExplorer onStartChat={() => window.location.assign("/")} />
        </main>
      </div>
    );
  }

  if (embedded) {
    return (
      <div className="app app--embedded">
        <main className="main">
          <CSAChatWidget embedded />
        </main>
      </div>
    );
  }

  return (
    <div className="app app--public">
      <main className="main csa-public">
        <section className="csa-public-card" aria-labelledby="csa-public-title">
          <span className="csa-public-icon" aria-hidden="true">
            <BsStars size={30} />
          </span>
          <p className="csa-public-eyebrow">Coordenação de Seleção e Admissão</p>
          <h1 id="csa-public-title">Assistente Virtual CSA</h1>
          <p>
            Tire dúvidas sobre processos seletivos, editais, matrículas e
            cronogramas com informações da CSA/UEFS.
          </p>
          <button type="button" className="csa-public-action" onClick={() => setChatOpen(true)}>
            Conversar com o assistente
          </button>
        </section>
        <CSAChatWidget
          initialOpen={chatOpen}
          onOpenChange={setChatOpen}
        />
      </main>
    </div>
  );
}
