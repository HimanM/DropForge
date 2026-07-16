import { useCallback, useEffect, useMemo, useState, type FormEvent, type ReactNode } from "react"
import {
  ArrowsClockwiseIcon,
  BroadcastIcon,
  CaretDownIcon,
  CaretUpIcon,
  CheckCircleIcon,
  ClockIcon,
  FloppyDiskIcon,
  GameControllerIcon,
  GearIcon,
  GiftIcon,
  GithubLogoIcon,
  GlobeIcon,
  HouseIcon,
  KeyIcon,
  LinkSimpleIcon,
  ListChecksIcon,
  MagnifyingGlassIcon,
  MoonIcon,
  PlayIcon,
  PlusIcon,
  PowerIcon,
  SignOutIcon,
  StopIcon,
  SunIcon,
  TerminalWindowIcon,
  TrashIcon,
  UsersIcon,
  WarningIcon,
  WifiHighIcon,
} from "@phosphor-icons/react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Progress, ProgressLabel } from "@/components/ui/progress"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"
import type { Campaign, MinerState, SessionMeta, Settings } from "@/types"

type Props = {
  session: SessionMeta
  onSignedOut: () => void
}

type Tab = "overview" | "campaigns" | "channels" | "games" | "settings" | "logs"

type SettingsChange = <K extends keyof Settings>(key: K, value: Settings[K]) => void

const PRIORITY_ONLY = "Priority list only"

const EMPTY_STATE: MinerState = {
  status: "Loading",
  icon_state: "idle",
  miner: { running: false, last_error: "" },
  login: { status: "", user_id: "-", activation_url: "", user_code: "" },
  current_drop: {},
  channels: [],
  campaigns: [],
  websockets: [],
  settings: {},
  selected_channel_id: null,
  logs: [],
}

async function readResponse(response: Response) {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(body.error || "The server could not complete that request.")
    Object.assign(error, { status: response.status })
    throw error
  }
  return body
}

function statusTone(status: string) {
  const value = status.toLowerCase()
  if (value.includes("active") || value.includes("online") || value.includes("watch")) return "text-emerald-600 dark:text-emerald-400"
  if (value.includes("upcoming") || value.includes("pending")) return "text-amber-600 dark:text-amber-400"
  if (value.includes("expired") || value.includes("offline") || value.includes("error")) return "text-red-600 dark:text-red-400"
  return "text-muted-foreground"
}

function percent(value = 0) {
  return `${Math.round(value * 1000) / 10}%`
}

function Metric({ label, value, icon }: { label: string; value: string | number; icon: ReactNode }) {
  return (
    <div className="min-w-0 border-l border-border pl-4 first:border-l-0 first:pl-0">
      <div className="mb-1 flex items-center gap-1.5 text-muted-foreground">{icon}<span className="text-xs">{label}</span></div>
      <p className="truncate text-xl font-semibold tracking-tight tabular-nums">{value}</p>
    </div>
  )
}

export function Dashboard({ session, onSignedOut }: Props) {
  const reduce = useReducedMotion()
  const [state, setState] = useState<MinerState>(EMPTY_STATE)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<Tab>("overview")
  const [busy, setBusy] = useState("")
  const [error, setError] = useState("")
  const [settingsDraft, setSettingsDraft] = useState<Partial<Settings>>({})
  const [settingsDirty, setSettingsDirty] = useState(false)
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = localStorage.getItem("dropforge-theme")
    return saved === "light" || saved === "dark"
      ? saved
      : window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
  })

  const api = useCallback(async (path: string, options: RequestInit = {}) => {
    const headers = new Headers(options.headers)
    if (options.body) headers.set("Content-Type", "application/json")
    if (options.method && options.method !== "GET") headers.set("X-CSRF-Token", session.csrf_token)
    try {
      return await readResponse(await fetch(path, { ...options, headers }))
    } catch (reason) {
      if (reason instanceof Error && (reason as Error & { status?: number }).status === 401) onSignedOut()
      throw reason
    }
  }, [onSignedOut, session.csrf_token])

  const load = useCallback(async (quiet = false) => {
    try {
      const next = await api("/api/state")
      setState(next as MinerState)
      setError("")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not reach the server.")
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [api])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => load(true), 2500)
    const refresh = () => load(true)
    window.addEventListener("focus", refresh)
    return () => {
      window.clearInterval(timer)
      window.removeEventListener("focus", refresh)
    }
  }, [load])

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    localStorage.setItem("dropforge-theme", theme)
  }, [theme])

  useEffect(() => {
    if (!settingsDirty) setSettingsDraft(state.settings.priority_mode === PRIORITY_ONLY ? state.settings : { ...state.settings, farm_unlinked: false })
  }, [settingsDirty, state.settings])

  async function runAction(name: string, path: string, options: RequestInit = { method: "POST" }) {
    setBusy(name)
    setError("")
    try {
      await api(path, options)
      await load(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Action failed.")
    } finally {
      setBusy("")
    }
  }

  async function logout() {
    await runAction("logout", "/api/logout")
    onSignedOut()
  }

  function changeSetting<K extends keyof Settings>(key: K, value: Settings[K]) {
    setSettingsDraft((current) => ({ ...current, [key]: value }))
    setSettingsDirty(true)
  }

  async function saveSettings(reload: boolean) {
    const name = reload ? "settings-reload" : "settings"
    setBusy(name)
    setError("")
    try {
      await api("/api/settings", { method: "PUT", body: JSON.stringify(settingsDraft) })
      if (reload) await api("/api/miner/reload", { method: "POST" })
      setSettingsDirty(false)
      await load(true)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Settings could not be saved.")
    } finally {
      setBusy("")
    }
  }

  const online = state.channels.filter((channel) => channel.status.toLowerCase().includes("online")).length
  const active = state.campaigns.filter((campaign) => campaign.active && !campaign.finished).length
  const current = state.current_drop

  const nav: { value: Tab; label: string; icon: ReactNode }[] = [
    { value: "overview", label: "Overview", icon: <HouseIcon /> },
    { value: "campaigns", label: "Campaigns", icon: <GiftIcon /> },
    { value: "channels", label: "Channels", icon: <BroadcastIcon /> },
    { value: "games", label: "Games", icon: <GameControllerIcon /> },
    { value: "settings", label: "Settings", icon: <GearIcon /> },
    { value: "logs", label: "Logs", icon: <TerminalWindowIcon /> },
  ]

  return (
    <main className="flex h-[100dvh] min-h-[100dvh] flex-col overflow-hidden bg-background text-foreground">
      <header className="z-40 shrink-0 border-b border-border/80 bg-background/92 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center gap-3 px-4 sm:px-6">
          <img className="size-9 rounded-xl ring-1 ring-border" src="/favicon-v2.png" alt="DropForge icon" />
          <div className="min-w-0">
            <p className="truncate font-semibold leading-tight tracking-tight">DropForge</p>
            <p className="truncate text-[11px] text-muted-foreground">Twitch Drops Miner</p>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <Badge className={cn("hidden sm:inline-flex", state.miner.running ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300" : "bg-muted text-muted-foreground")} variant="secondary">
              {state.miner.running ? "Miner running" : "Miner stopped"}
            </Badge>
            <Button aria-label={`Use ${theme === "dark" ? "light" : "dark"} theme`} size="icon" variant="ghost" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <SunIcon /> : <MoonIcon />}</Button>
            <Button aria-label="Log out" size="icon" variant="ghost" disabled={busy === "logout"} onClick={logout}><SignOutIcon /></Button>
          </div>
        </div>
      </header>

      <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)} className="mx-auto min-h-0 w-full max-w-[1500px] flex-1 flex-col overflow-hidden px-4 sm:px-6">
        <div className="z-30 -mx-4 shrink-0 overflow-x-auto border-b border-border/70 bg-background/92 px-4 backdrop-blur-xl sm:-mx-6 sm:px-6">
          <TabsList className="h-12 w-max gap-2 bg-transparent p-0" variant="line">
            {nav.map((item) => <TabsTrigger key={item.value} value={item.value} className="h-11 gap-2 px-3" aria-label={item.label}>{item.icon}<span className="hidden sm:inline">{item.label}</span></TabsTrigger>)}
          </TabsList>
        </div>

        {error && <div className="mt-4 flex shrink-0 items-start gap-2 rounded-xl border border-red-500/25 bg-red-500/8 p-3 text-sm text-red-700 dark:text-red-300" role="alert"><WarningIcon className="mt-0.5 shrink-0" />{error}</div>}

        <TabsContent value="overview" className="scrollbar-theme min-h-0 overflow-y-auto py-5 pr-1">
          {loading ? <OverviewSkeleton /> : (
            <motion.div initial={reduce ? false : { opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="space-y-5 pb-1">
              <section className="grid overflow-hidden rounded-2xl border border-border bg-card lg:grid-cols-[minmax(0,1fr)_280px]">
                <div className="order-2 flex min-h-60 flex-col justify-between p-5 lg:order-1">
                  <div>
                    <div className="mb-5 flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className={statusTone(state.status)}>{state.status}</Badge>
                      {state.login.user_id !== "-" && <span className="text-xs text-muted-foreground">Twitch user {state.login.user_id}</span>}
                    </div>
                    <h1 className="max-w-2xl text-3xl font-semibold leading-tight tracking-[-0.04em]">
                      {state.miner.running ? (current.game && current.game !== "..." ? current.game : "Miner is finding the next drop") : "Miner is ready when you are"}
                    </h1>
                    <p className="mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground">
                      {state.miner.running ? (current.campaign || "Inventory and channel state update automatically.") : "Start mining without restarting the web control room."}
                    </p>
                  </div>

                  <div className="mt-6 flex flex-wrap gap-2">
                    {state.miner.running ? (
                      <Button variant="destructive" disabled={busy === "stop"} onClick={() => runAction("stop", "/api/miner/stop")}><StopIcon data-icon="inline-start" />{busy === "stop" ? "Stopping" : "Stop miner"}</Button>
                    ) : (
                      <Button disabled={busy === "start"} onClick={() => runAction("start", "/api/miner/start")}><PlayIcon data-icon="inline-start" />{busy === "start" ? "Starting" : "Start miner"}</Button>
                    )}
                    <Button variant="outline" disabled={!state.miner.running || busy === "reload"} onClick={() => runAction("reload", "/api/miner/reload")}><ArrowsClockwiseIcon data-icon="inline-start" />Reload inventory</Button>
                  </div>
                </div>
                <div className="order-1 min-h-60 bg-muted lg:order-2 lg:min-h-full">
                  {current.category_image_url ? <img className="h-full max-h-[300px] w-full object-cover object-top" src={current.category_image_url} alt={`${current.game || "Current game"} category art`} /> : <div className="flex h-full min-h-60 items-center justify-center text-muted-foreground"><GameControllerIcon className="size-14" /></div>}
                </div>
              </section>

              {state.login.activation_url && (
                <section className="rounded-2xl border border-orange-500/25 bg-orange-500/8 p-5 sm:flex sm:items-center sm:justify-between sm:gap-6">
                  <div>
                    <p className="font-semibold">Connect Twitch</p>
                    <p className="mt-1 text-sm text-muted-foreground">Open Twitch activation and enter code <strong className="text-foreground">{state.login.user_code}</strong>.</p>
                  </div>
                  <a className="mt-4 inline-flex h-9 items-center gap-2 rounded-lg bg-primary px-3 text-sm font-medium text-primary-foreground sm:mt-0" href={state.login.activation_url} rel="noreferrer" target="_blank">Open Twitch<LinkSimpleIcon /></a>
                </section>
              )}

              <section className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                <Metric label="Active campaigns" value={active} icon={<GiftIcon />} />
                <Metric label="Online channels" value={online} icon={<UsersIcon />} />
                <Metric label="Websocket topics" value={state.websockets.reduce((sum, socket) => sum + socket.topics, 0)} icon={<WifiHighIcon />} />
                <Metric label="Miner state" value={state.miner.running ? "Online" : "Stopped"} icon={<PowerIcon />} />
              </section>

              <section className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(280px,.7fr)]">
                <div className="rounded-2xl border border-border bg-card p-5">
                  <div className="mb-4 flex items-center justify-between gap-4"><div><h2 className="text-lg font-semibold tracking-tight">Current progress</h2><p className="mt-1 text-sm text-muted-foreground">{current.rewards || "No reward selected yet"}</p></div><span className="text-sm tabular-nums text-muted-foreground">{current.remaining || "--:--:--"}</span></div>
                  <div className="space-y-3">
                    <Progress value={(current.drop_progress || 0) * 100}><ProgressLabel>Drop</ProgressLabel><span className="ml-auto text-sm tabular-nums text-muted-foreground">{percent(current.drop_progress)}</span></Progress>
                    <Progress value={(current.campaign_progress || 0) * 100}><ProgressLabel>Campaign</ProgressLabel><span className="ml-auto text-sm tabular-nums text-muted-foreground">{percent(current.campaign_progress)}</span></Progress>
                  </div>
                  {current.benefits && current.benefits.length > 0 && <div className="scrollbar-theme mt-4 flex gap-3 overflow-x-auto pb-2">{current.benefits.map((benefit) => <div key={`${benefit.name}-${benefit.image_url}`} className="flex min-w-40 items-center gap-3 rounded-xl bg-muted p-2.5"><img className="size-12 rounded-lg object-cover" src={benefit.image_url} alt={benefit.name} /><span className="line-clamp-2 text-xs font-medium">{benefit.name}</span></div>)}</div>}
                </div>
                <div className="rounded-2xl border border-border bg-card p-5">
                  <h2 className="text-lg font-semibold tracking-tight">Watching now</h2>
                  {state.channels.find((channel) => channel.watching) ? (() => { const channel = state.channels.find((item) => item.watching)!; return <div className="mt-6"><div className="flex size-11 items-center justify-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"><BroadcastIcon className="size-5" /></div><p className="mt-4 font-semibold">{channel.name}</p><p className="mt-1 text-sm text-muted-foreground">{channel.game || "Twitch stream"}</p><p className="mt-5 text-xs text-muted-foreground">{channel.viewers || "0"} viewers</p></div> })() : <div className="mt-8 text-sm leading-relaxed text-muted-foreground">The miner will choose an eligible live channel when a campaign is ready.</div>}
                </div>
              </section>
            </motion.div>
          )}
        </TabsContent>

        <TabsContent value="campaigns" className="min-h-0 overflow-hidden pt-5"><Campaigns campaigns={state.campaigns} /></TabsContent>
        <TabsContent value="channels" className="min-h-0 overflow-hidden pt-5"><Channels state={state} busy={busy} onSelect={(id) => runAction("channel", "/api/channels/select", { method: "POST", body: JSON.stringify({ channel_id: id }) })} /></TabsContent>
        <TabsContent value="games" className="min-h-0 overflow-hidden pt-5"><GameRules draft={settingsDraft} dirty={settingsDirty} busy={busy} onChange={changeSetting} onSave={saveSettings} /></TabsContent>
        <TabsContent value="settings" className="min-h-0 overflow-hidden pt-5"><SettingsPanel draft={settingsDraft} dirty={settingsDirty} busy={busy} session={session} onSignedOut={onSignedOut} onChange={changeSetting} onSave={saveSettings} onInvalidate={() => runAction("invalidate", "/api/miner/invalidate-auth")} /></TabsContent>
        <TabsContent value="logs" className="min-h-0 overflow-hidden pt-5"><Logs logs={state.logs} /></TabsContent>
      </Tabs>

      <footer className="shrink-0 border-t border-border bg-background">
        <div className="mx-auto flex max-w-[1500px] flex-col gap-2 px-4 py-3 text-xs text-muted-foreground sm:flex-row sm:items-center sm:justify-between sm:px-6">
          <span>DropForge {session.version.replaceAll("_", " ")}. Self-hosted Twitch Drops Miner.</span>
          <div className="flex flex-wrap gap-4"><a className="hover:text-foreground" href="https://www.twitch.tv/drops/inventory" rel="noreferrer" target="_blank">Twitch inventory</a><a className="hover:text-foreground" href="https://www.twitch.tv/drops/campaigns" rel="noreferrer" target="_blank">All campaigns</a><a className="flex items-center gap-1 hover:text-foreground" href="https://github.com/HimanM" rel="noreferrer" target="_blank"><GithubLogoIcon /> HimanM</a></div>
        </div>
      </footer>
    </main>
  )
}

function OverviewSkeleton() {
  return <div className="space-y-7"><Skeleton className="h-[420px] rounded-2xl" /><div className="grid grid-cols-2 gap-5 sm:grid-cols-4">{Array.from({ length: 4 }, (_, index) => <Skeleton key={index} className="h-16" />)}</div><div className="grid gap-5 lg:grid-cols-2"><Skeleton className="h-64 rounded-2xl" /><Skeleton className="h-64 rounded-2xl" /></div></div>
}

function PageFrame({ title, description, actions, children }: { title: string; description: string; actions?: ReactNode; children: ReactNode }) {
  return <section className="flex h-full min-h-0 flex-col">
    <div className="flex shrink-0 flex-col gap-4 pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div><h1 className="text-2xl font-semibold tracking-[-0.03em]">{title}</h1><p className="mt-1 text-sm text-muted-foreground">{description}</p></div>
      {actions}
    </div>
    <div className="scrollbar-theme min-h-0 flex-1 overflow-y-auto overscroll-contain pb-6 pr-1">{children}</div>
  </section>
}

function Campaigns({ campaigns }: { campaigns: Campaign[] }) {
  const [query, setQuery] = useState("")
  const [filter, setFilter] = useState<"available" | "all" | "finished">("available")
  const visible = useMemo(() => campaigns.filter((campaign) => {
    const matches = `${campaign.game} ${campaign.name}`.toLowerCase().includes(query.toLowerCase())
    if (!matches) return false
    if (filter === "finished") return campaign.finished
    if (filter === "available") return !campaign.finished && !campaign.expired && !campaign.excluded
    return true
  }), [campaigns, filter, query])

  const controls = <div className="flex gap-2"><div className="relative flex-1"><MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input className="h-9 min-w-0 pl-9 sm:w-64" placeholder="Search campaigns" value={query} onChange={(event) => setQuery(event.target.value)} /></div><select className="h-9 rounded-lg border border-input bg-background px-2 text-sm" value={filter} onChange={(event) => setFilter(event.target.value as typeof filter)}><option value="available">Available</option><option value="all">All</option><option value="finished">Finished</option></select></div>

  return <PageFrame title="Campaigns" description="Category art, rewards, eligibility, and progress from Twitch." actions={controls}>
    {visible.length === 0 ? <div className="rounded-2xl border border-dashed border-border p-12 text-center"><GiftIcon className="mx-auto size-8 text-muted-foreground" /><p className="mt-4 font-medium">No campaigns match</p><p className="mt-1 text-sm text-muted-foreground">Try another filter or reload the inventory.</p></div> : <div className="grid gap-5 xl:grid-cols-2">{visible.map((campaign) => <CampaignCard key={campaign.id} campaign={campaign} />)}</div>}
  </PageFrame>
}

function CampaignCard({ campaign }: { campaign: Campaign }) {
  return <article className="grid overflow-hidden rounded-2xl border border-border bg-card sm:grid-cols-[150px_minmax(0,1fr)]">
    <img className="h-52 w-full object-cover object-top sm:h-full" src={campaign.category_image_url} alt={`${campaign.game} category art`} loading="lazy" />
    <div className="min-w-0 p-4 sm:p-5">
      <div className="flex items-start justify-between gap-4"><div className="min-w-0"><p className="truncate text-sm font-semibold">{campaign.game}</p><h2 className="mt-1 line-clamp-2 text-base leading-snug text-muted-foreground">{campaign.name}</h2></div><Badge variant="secondary" className={statusTone(campaign.status)}>{campaign.status}</Badge></div>
      <div className="mt-4 flex flex-wrap gap-x-4 gap-y-2 text-xs text-muted-foreground"><span className="flex items-center gap-1.5"><ClockIcon />Ends {new Date(campaign.ends).toLocaleDateString()}</span><span className={campaign.linked ? "text-emerald-600 dark:text-emerald-400" : "text-amber-600 dark:text-amber-400"}>{campaign.linked ? "Account linked" : "Link required"}</span></div>
      <Progress className="mt-5" value={campaign.progress * 100}><ProgressLabel>Progress</ProgressLabel><span className="ml-auto text-sm tabular-nums text-muted-foreground">{percent(campaign.progress)}</span></Progress>
      <div className="scrollbar-theme mt-5 flex gap-2 overflow-x-auto pb-2">{campaign.drops.flatMap((drop) => drop.benefits.map((benefit) => <div key={`${drop.id}-${benefit.id || benefit.name}`} className="min-w-28 rounded-xl bg-muted p-2"><img className="aspect-square w-full rounded-lg object-cover" src={benefit.image_url} alt={benefit.name} loading="lazy" /><p className="mt-2 line-clamp-2 text-[11px] font-medium leading-snug">{benefit.name}</p><p className="mt-1 text-[10px] text-muted-foreground">{drop.claimed ? "Claimed" : `${drop.current_minutes}/${drop.required_minutes} min`}</p></div>))}</div>
      {!campaign.linked && campaign.link_url && <a className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-primary hover:underline" href={campaign.link_url} rel="noreferrer" target="_blank">Link game account<LinkSimpleIcon /></a>}
    </div>
  </article>
}

function Channels({ state, busy, onSelect }: { state: MinerState; busy: string; onSelect: (id: string) => void }) {
  return <PageFrame title="Channels" description="Inspect candidates and switch the active stream.">{state.channels.length === 0 ? <div className="rounded-2xl border border-dashed border-border p-12 text-center text-sm text-muted-foreground">Channels appear after inventory discovery.</div> : <div className="grid gap-3 lg:grid-cols-2">{state.channels.map((channel) => <div key={channel.iid} className={cn("flex items-center gap-4 rounded-2xl border bg-card p-4", channel.watching ? "border-emerald-500/35" : "border-border")}><div className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl bg-muted", channel.watching && "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400")}><BroadcastIcon className="size-5" /></div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><p className="truncate font-semibold">{channel.name}</p>{channel.watching && <Badge variant="secondary">Watching</Badge>}</div><p className="mt-1 truncate text-xs text-muted-foreground">{channel.game || "No category"} · {channel.viewers || "0"} viewers · {channel.drops ? "Drops enabled" : "No drops"}</p></div><Button size="sm" variant="outline" disabled={channel.watching || busy === "channel" || !state.miner.running} onClick={() => onSelect(channel.iid)}>Watch</Button></div>)}</div>}</PageFrame>
}

function GameRules({ draft, dirty, busy, onChange, onSave }: { draft: Partial<Settings>; dirty: boolean; busy: string; onChange: SettingsChange; onSave: (reload: boolean) => void }) {
  const add = (key: "priority" | "exclude", game: string) => { if (!draft[key]?.includes(game)) onChange(key, [...(draft[key] || []), game]) }
  const remove = (key: "priority" | "exclude", game: string) => onChange(key, (draft[key] || []).filter((item) => item !== game))
  const move = (game: string, offset: number) => { const list = [...(draft.priority || [])]; const index = list.indexOf(game); const next = Math.max(0, Math.min(list.length - 1, index + offset)); if (index === next) return; list.splice(index, 1); list.splice(next, 0, game); onChange("priority", list) }

  return <PageFrame title="Game rules" description="Choose priority order and games the miner should ignore." actions={<SaveActions dirty={dirty} busy={busy} onSave={onSave} />}>
    <div className="grid gap-5 xl:grid-cols-2">
      <SettingsGroup title="Priority games" icon={<GameControllerIcon />}>
        <div className="flex items-center justify-between gap-4"><p className="text-sm text-muted-foreground">The miner checks these games in order.</p><GamePicker title="Add priority games" available={draft.available_games || []} selected={draft.priority || []} onAdd={(game) => add("priority", game)} /></div>
        <GameList games={draft.priority || []} onRemove={(game) => remove("priority", game)} onMove={move} />
      </SettingsGroup>
      <SettingsGroup title="Excluded games" icon={<TrashIcon />}>
        <div className="flex items-center justify-between gap-4"><p className="text-sm text-muted-foreground">Campaigns for these games are skipped.</p><GamePicker title="Exclude games" available={draft.available_games || []} selected={draft.exclude || []} onAdd={(game) => add("exclude", game)} /></div>
        <GameList games={draft.exclude || []} onRemove={(game) => remove("exclude", game)} />
      </SettingsGroup>
    </div>
  </PageFrame>
}

function GamePicker({ title, available, selected, onAdd }: { title: string; available: string[]; selected: string[]; onAdd: (game: string) => void }) {
  const [query, setQuery] = useState("")
  const visible = useMemo(() => Array.from(new Set(available)).filter((game) => game.toLowerCase().includes(query.toLowerCase())), [available, query])

  return <Dialog>
    <DialogTrigger render={<Button variant="outline" />}><PlusIcon />Add game</DialogTrigger>
    <DialogContent className="inset-y-0 right-0 left-auto top-0 h-[100dvh] max-h-none w-full max-w-md translate-x-0 translate-y-0 grid-rows-[auto_auto_minmax(0,1fr)_auto] gap-0 rounded-none border-l border-border p-0 data-open:slide-in-from-right-4 data-closed:slide-out-to-right-4 sm:rounded-l-2xl">
      <DialogHeader className="border-b border-border px-5 py-5"><DialogTitle>{title}</DialogTitle><DialogDescription>Search the Twitch inventory and add one or more games.</DialogDescription></DialogHeader>
      <div className="border-b border-border p-4"><div className="relative"><MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" /><Input className="pl-9" autoFocus placeholder="Search games" value={query} onChange={(event) => setQuery(event.target.value)} /></div></div>
      <div className="scrollbar-theme min-h-0 overflow-y-auto p-3">
        {visible.length === 0 ? <div className="p-8 text-center text-sm text-muted-foreground">No games match your search.</div> : <div className="grid gap-1">{visible.map((game) => { const chosen = selected.includes(game); return <button type="button" key={game} disabled={chosen} onClick={() => onAdd(game)} className="flex min-h-11 w-full items-center justify-between gap-4 rounded-xl px-3 py-2 text-left text-sm font-medium transition-colors hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-60"><span className="min-w-0 truncate">{game}</span>{chosen ? <CheckCircleIcon className="shrink-0 text-primary" /> : <PlusIcon className="shrink-0 text-muted-foreground" />}</button> })}</div>}
      </div>
      <div className="border-t border-border px-5 py-3 text-xs text-muted-foreground">{selected.length} selected</div>
    </DialogContent>
  </Dialog>
}

function SaveActions({ dirty, busy, onSave }: { dirty: boolean; busy: string; onSave: (reload: boolean) => void }) {
  const saving = busy === "settings" || busy === "settings-reload"
  return <div className="flex flex-wrap gap-2"><Button variant="outline" disabled={!dirty || saving} onClick={() => onSave(false)}><FloppyDiskIcon />{busy === "settings" ? "Saving" : "Save"}</Button><Button disabled={saving} onClick={() => onSave(true)}><ArrowsClockwiseIcon />{busy === "settings-reload" ? "Saving and reloading" : "Save and reload"}</Button></div>
}

function SettingsPanel({ draft, dirty, busy, session, onChange, onSave, onInvalidate, onSignedOut }: { draft: Partial<Settings>; dirty: boolean; busy: string; session: SessionMeta; onChange: SettingsChange; onSave: (reload: boolean) => void; onInvalidate: () => void; onSignedOut: () => void }) {
  const priorityOnly = draft.priority_mode === PRIORITY_ONLY
  const setPriorityMode = (value: string) => { onChange("priority_mode", value); if (value !== PRIORITY_ONLY) onChange("farm_unlinked", false) }

  return <PageFrame title="Settings" description="Mining behavior, connection, and web access." actions={<SaveActions dirty={dirty} busy={busy} onSave={onSave} />}>
    <div className="grid gap-5 xl:grid-cols-2">
      <SettingsGroup title="Mining behavior" icon={<ListChecksIcon />}>
        <Field label="Priority mode" description="Controls how eligible campaigns are ordered."><select className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm" value={draft.priority_mode || ""} onChange={(event) => setPriorityMode(event.target.value)}>{(draft.priority_modes || []).map((mode) => <option key={mode}>{mode}</option>)}</select></Field>
        <Toggle label="Farm unlinked drops" description={priorityOnly ? "Farm campaigns that do not require a linked game account." : "Available only when Priority mode is Priority list only."} checked={priorityOnly && Boolean(draft.farm_unlinked)} disabled={!priorityOnly} onChange={(value) => onChange("farm_unlinked", value)} />
        <Toggle label="Badge and emote drops" description="Include campaigns whose rewards are badges or emotes." checked={Boolean(draft.enable_badges_emotes)} onChange={(value) => onChange("enable_badges_emotes", value)} />
        <Toggle label="Extra availability check" description="Run the additional Twitch availability lookup." checked={Boolean(draft.available_drops_check)} onChange={(value) => onChange("available_drops_check", value)} />
      </SettingsGroup>
      <SettingsGroup title="Connection" icon={<GlobeIcon />}>
        <Field label="Proxy URL" description="Optional HTTP or HTTPS proxy. Restart the miner after changing it."><Input value={draft.proxy || ""} placeholder="https://proxy.example:8080" onChange={(event) => onChange("proxy", event.target.value)} /></Field>
        <Field label="Language" description="Used for miner status messages after restart."><select className="h-9 w-full rounded-lg border border-input bg-background px-3 text-sm" value={draft.language || "English"} onChange={(event) => onChange("language", event.target.value)}>{(draft.languages || ["English"]).map((language) => <option key={language}>{language}</option>)}</select></Field>
        <Field label={`Connection quality: ${draft.connection_quality || 1}`} description="Higher values use longer network timeouts for slower connections."><input className="w-full accent-[var(--primary)]" type="range" min="1" max="6" value={draft.connection_quality || 1} onChange={(event) => onChange("connection_quality", Number(event.target.value))} /></Field>
      </SettingsGroup>
      <SettingsGroup title="Security" icon={<KeyIcon />}>
        <p className="text-sm leading-relaxed text-muted-foreground">Changing the admin password revokes every browser session. Invalidating Twitch auth removes the saved Twitch token and starts device login again.</p>
        <div className="flex flex-wrap gap-2"><PasswordDialog session={session} onSignedOut={onSignedOut} /><Button variant="destructive" disabled={busy === "invalidate"} onClick={onInvalidate}>Reset Twitch login</Button></div>
      </SettingsGroup>
    </div>
  </PageFrame>
}

function SettingsGroup({ title, icon, children }: { title: string; icon: ReactNode; children: ReactNode }) { return <div className="rounded-2xl border border-border bg-card p-5"><div className="mb-5 flex items-center gap-2"><span className="text-primary">{icon}</span><h2 className="font-semibold">{title}</h2></div><div className="space-y-5">{children}</div></div> }
function Field({ label, description, children }: { label: string; description: string; children: ReactNode }) { return <div className="space-y-2"><div><p className="text-sm font-medium">{label}</p><p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p></div>{children}</div> }
function Toggle({ label, description, checked, disabled = false, onChange }: { label: string; description: string; checked: boolean; disabled?: boolean; onChange: (value: boolean) => void }) { return <div className={cn("flex items-center justify-between gap-5", disabled && "opacity-60")}><div><p className="text-sm font-medium">{label}</p><p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{description}</p></div><Switch checked={checked} disabled={disabled} onCheckedChange={onChange} aria-label={label} /></div> }
function GameList({ games, onRemove, onMove }: { games: string[]; onRemove: (game: string) => void; onMove?: (game: string, offset: number) => void }) { return games.length === 0 ? <p className="text-sm text-muted-foreground">No games added.</p> : <div className="space-y-2">{games.map((game, index) => <div className="flex items-center gap-2 rounded-xl bg-muted px-3 py-2" key={game}><span className="min-w-0 flex-1 truncate text-sm">{game}</span>{onMove && <><Button size="icon-xs" variant="ghost" aria-label={`Move ${game} up`} disabled={index === 0} onClick={() => onMove(game, -1)}><CaretUpIcon /></Button><Button size="icon-xs" variant="ghost" aria-label={`Move ${game} down`} disabled={index === games.length - 1} onClick={() => onMove(game, 1)}><CaretDownIcon /></Button></>}<Button size="icon-xs" variant="ghost" aria-label={`Remove ${game}`} onClick={() => onRemove(game)}><TrashIcon /></Button></div>)}</div> }

function PasswordDialog({ session, onSignedOut }: { session: SessionMeta; onSignedOut: () => void }) {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await readResponse(await fetch("/api/password/change", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token }, body: JSON.stringify({ current_password: current, new_password: next }) })); onSignedOut() } catch (reason) { setError(reason instanceof Error ? reason.message : "Password change failed.") } finally { setBusy(false) } }
  return <Dialog><DialogTrigger render={<Button variant="outline" />}>Change admin password</DialogTrigger><DialogContent><DialogHeader><DialogTitle>Change admin password</DialogTitle><DialogDescription>All signed-in browsers will be logged out.</DialogDescription></DialogHeader><form className="space-y-4" onSubmit={submit}><Field label="Current password" description="Confirm the existing administrator password."><Input type="password" autoComplete="current-password" value={current} onChange={(event) => setCurrent(event.target.value)} required /></Field><Field label="New password" description="Use at least 12 characters."><Input type="password" autoComplete="new-password" minLength={12} value={next} onChange={(event) => setNext(event.target.value)} required /></Field>{error && <p className="text-sm text-destructive" role="alert">{error}</p>}<Button className="w-full" disabled={busy} type="submit">{busy ? "Changing" : "Change password"}</Button></form></DialogContent></Dialog>
}

function Logs({ logs }: { logs: string[] }) {
  return <PageFrame title="Logs" description="The latest 200 miner messages."><div className="scrollbar-theme min-h-80 overflow-auto rounded-2xl border border-border bg-[#171614] p-4 text-stone-300"><pre className="font-mono text-xs leading-6">{logs.length ? logs.join("\n") : "No log messages yet."}</pre></div></PageFrame>
}
