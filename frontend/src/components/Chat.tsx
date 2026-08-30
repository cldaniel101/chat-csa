import { useSearchParams } from "react-router-dom";
import type { AgentId } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { CSAChatWidget } from "./chat/CSAChatWidget";

export default function Chat() {
  const [search] = useSearchParams();
  const agent = (search.get("agent") as AgentId) || "consumer";
  const { token, isAuthenticated } = useAuth();

  return (
    <CSAChatWidget
      agent={agent}
      token={agent === "ingester" ? token : null}
      isAuthenticated={isAuthenticated}
    />
  );
}
