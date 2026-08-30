import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import Admin from "./components/Admin";
import Chat from "./components/Chat";
import Login from "./components/Login";
import "./App.css";

function AppRoutes() {
  return (
    <main className="main">
      <Routes>
        <Route path="/" element={<Navigate to="/chat?agent=consumer" replace />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/login" element={<Login />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="*" element={<Navigate to="/chat?agent=consumer" replace />} />
      </Routes>
    </main>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <div className="app">
          <AppRoutes />
        </div>
      </AuthProvider>
    </BrowserRouter>
  );
}
