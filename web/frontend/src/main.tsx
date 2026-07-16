import React, { useEffect, useState } from "react"
import ReactDOM from "react-dom/client"
import "@fontsource-variable/manrope"

import { AuthScreen } from "@/auth-screen"
import { Dashboard } from "@/dashboard"
import type { SessionMeta } from "@/types"
import "./index.css"

function App() {
  const [session, setSession] = useState<SessionMeta | null>(null)
  const [checking, setChecking] = useState(true)

  useEffect(() => {
    fetch("/api/session")
      .then((response) => response.ok ? response.json() : null)
      .then((value) => setSession(value))
      .finally(() => setChecking(false))
  }, [])

  if (checking) return <main className="grid min-h-[100dvh] place-items-center bg-[#11100e]"><img className="size-16 animate-pulse rounded-2xl" src="/favicon-v2.png" alt="DropForge loading" /></main>
  if (!session) return <AuthScreen onAuthenticated={setSession} />
  return <Dashboard session={session} onSignedOut={() => setSession(null)} />
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
