import { useState, type FormEvent } from "react"
import {
  ArrowRightIcon,
  CheckIcon,
  CopyIcon,
  EyeIcon,
  EyeSlashIcon,
  GithubLogoIcon,
  KeyIcon,
  LockKeyOpenIcon,
  ShieldCheckIcon,
} from "@phosphor-icons/react"
import { motion, useReducedMotion } from "motion/react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SessionMeta } from "@/types"

type Props = { onAuthenticated: (session: SessionMeta) => void }

async function responseJson(response: Response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.error || "The server could not complete that request.")
  return body
}

export function AuthScreen({ onAuthenticated }: Props) {
  const reduce = useReducedMotion()
  const [view, setView] = useState<"login" | "reset" | "recovery">("login")
  const [password, setPassword] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [recovery, setRecovery] = useState("")
  const [nextRecovery, setNextRecovery] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [busy, setBusy] = useState(false)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState("")

  async function login(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      await responseJson(
        await fetch("/api/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password }),
        }),
      )
      const session = await responseJson(await fetch("/api/session"))
      onAuthenticated(session as SessionMeta)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Login failed.")
    } finally {
      setBusy(false)
    }
  }

  async function reset(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError("")
    try {
      const body = await responseJson(
        await fetch("/api/password/reset", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ recovery_code: recovery, new_password: newPassword }),
        }),
      )
      setNextRecovery(body.recovery_code)
      setPassword("")
      setNewPassword("")
      setRecovery("")
      setView("recovery")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Password reset failed.")
    } finally {
      setBusy(false)
    }
  }

  async function copyRecovery() {
    await navigator.clipboard.writeText(nextRecovery)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1500)
  }

  return (
    <main className="relative grid min-h-[100dvh] overflow-hidden bg-[#11100e] text-stone-100 lg:grid-cols-[1.08fr_.92fr]">
      <section className="relative hidden min-h-[100dvh] overflow-hidden border-r border-white/8 p-10 lg:flex lg:flex-col lg:justify-between">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_22%_18%,rgba(194,93,38,.22),transparent_30%),radial-gradient(circle_at_70%_82%,rgba(255,255,255,.06),transparent_32%)]" />
        <div className="relative flex items-center gap-3">
          <img className="size-12 rounded-[14px] ring-1 ring-white/15" src="/favicon-v2.png" alt="DropForge icon" />
          <div>
            <p className="text-lg font-semibold tracking-tight">DropForge</p>
            <p className="text-xs text-stone-400">Private mining control room</p>
          </div>
        </div>
        <motion.div
          className="relative max-w-xl"
          initial={reduce ? false : { opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
        >
          <p className="mb-5 max-w-md text-5xl font-semibold leading-[1.02] tracking-[-0.045em]">
            Drops keep moving. Your miner stays close.
          </p>
          <p className="max-w-md text-base leading-relaxed text-stone-400">
            Control campaigns, channels, settings, and Twitch device login from one private server.
          </p>
        </motion.div>
        <div className="relative flex gap-8 text-sm text-stone-400">
          <span className="flex items-center gap-2"><ShieldCheckIcon className="size-4 text-orange-400" /> Salted scrypt passwords</span>
          <span className="flex items-center gap-2"><LockKeyOpenIcon className="size-4 text-orange-400" /> Revocable sessions</span>
        </div>
      </section>

      <section className="flex min-h-[100dvh] flex-col px-5 py-6 sm:px-10 lg:px-16">
        <div className="flex items-center gap-3 lg:hidden">
          <img className="size-10 rounded-xl ring-1 ring-white/15" src="/favicon-v2.png" alt="DropForge icon" />
          <div>
            <p className="font-semibold tracking-tight">DropForge</p>
            <p className="text-xs text-stone-500">Private mining control room</p>
          </div>
        </div>

        <div className="my-auto w-full max-w-md self-center py-12">
          {view === "login" && (
            <motion.div initial={reduce ? false : { opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}>
              <h1 className="text-3xl font-semibold tracking-[-0.035em]">Welcome back</h1>
              <p className="mt-2 text-sm leading-relaxed text-stone-400">Sign in to manage the miner on this server.</p>
              <form className="mt-8 space-y-5" onSubmit={login}>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-stone-200" htmlFor="password">Admin password</label>
                  <div className="relative">
                    <Input
                      id="password"
                      autoComplete="current-password"
                      className="h-11 border-white/12 bg-white/6 pr-11 text-stone-100 placeholder:text-stone-600 focus-visible:border-orange-400"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(event) => setPassword(event.target.value)}
                      required
                    />
                    <button
                      className="absolute inset-y-0 right-0 flex w-11 items-center justify-center text-stone-500 hover:text-stone-200"
                      type="button"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      onClick={() => setShowPassword((value) => !value)}
                    >
                      {showPassword ? <EyeSlashIcon /> : <EyeIcon />}
                    </button>
                  </div>
                  {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
                </div>
                <Button className="h-11 w-full bg-orange-600 text-white hover:bg-orange-500" disabled={busy} type="submit">
                  {busy ? "Signing in" : "Sign in"}<ArrowRightIcon data-icon="inline-end" />
                </Button>
              </form>
              <button className="mt-5 text-sm text-stone-400 underline-offset-4 hover:text-stone-100 hover:underline" onClick={() => { setError(""); setView("reset") }}>
                Forgot your password?
              </button>
            </motion.div>
          )}

          {view === "reset" && (
            <motion.div initial={reduce ? false : { opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }}>
              <div className="mb-6 flex size-11 items-center justify-center rounded-xl bg-orange-500/12 text-orange-400"><KeyIcon className="size-5" /></div>
              <h1 className="text-3xl font-semibold tracking-[-0.035em]">Reset password</h1>
              <p className="mt-2 text-sm leading-relaxed text-stone-400">Use the recovery code printed during installation. Resetting revokes every browser session.</p>
              <form className="mt-8 space-y-5" onSubmit={reset}>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="recovery">Recovery code</label>
                  <Input id="recovery" autoComplete="off" className="h-11 border-white/12 bg-white/6 text-stone-100" value={recovery} onChange={(event) => setRecovery(event.target.value)} required />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="new-password">New password</label>
                  <Input id="new-password" autoComplete="new-password" className="h-11 border-white/12 bg-white/6 text-stone-100" type="password" minLength={12} value={newPassword} onChange={(event) => setNewPassword(event.target.value)} required />
                  <p className="text-xs text-stone-500">Use at least 12 characters.</p>
                </div>
                {error && <p className="text-sm text-red-400" role="alert">{error}</p>}
                <Button className="h-11 w-full bg-orange-600 text-white hover:bg-orange-500" disabled={busy} type="submit">{busy ? "Resetting" : "Reset password"}</Button>
              </form>
              <button className="mt-5 text-sm text-stone-400 hover:text-stone-100" onClick={() => { setError(""); setView("login") }}>Back to sign in</button>
            </motion.div>
          )}

          {view === "recovery" && (
            <motion.div initial={reduce ? false : { opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
              <div className="mb-6 flex size-11 items-center justify-center rounded-xl bg-emerald-500/12 text-emerald-400"><ShieldCheckIcon className="size-5" /></div>
              <h1 className="text-3xl font-semibold tracking-[-0.035em]">Password reset</h1>
              <p className="mt-2 text-sm leading-relaxed text-stone-400">Save this new one-time recovery code before signing in.</p>
              <div className="mt-7 rounded-xl border border-white/10 bg-white/5 p-4">
                <code className="break-all text-sm text-stone-100">{nextRecovery}</code>
                <Button className="mt-4 w-full" variant="outline" onClick={copyRecovery}>
                  {copied ? <CheckIcon /> : <CopyIcon />}{copied ? "Copied" : "Copy recovery code"}
                </Button>
              </div>
              <Button className="mt-5 h-11 w-full bg-orange-600 text-white hover:bg-orange-500" onClick={() => setView("login")}>Continue to sign in</Button>
            </motion.div>
          )}
        </div>

        <footer className="flex items-center justify-between text-xs text-stone-600">
          <span>Self-hosted on your server</span>
          <a className="flex items-center gap-1.5 hover:text-stone-300" href="https://github.com/HimanM" rel="noreferrer" target="_blank"><GithubLogoIcon /> HimanM</a>
        </footer>
      </section>
    </main>
  )
}
