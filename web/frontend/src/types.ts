export type SessionMeta = {
  authenticated: true
  csrf_token: string
  name: string
  version: string
  password_min_length: number
}

export type Benefit = { id?: string; name: string; image_url: string }

export type Drop = {
  id: string
  name: string
  progress: number
  current_minutes: number
  required_minutes: number
  claimed: boolean
  claimable: boolean
  starts: string
  ends: string
  benefits: Benefit[]
}

export type Campaign = {
  id: string
  name: string
  game: string
  status: string
  linked: boolean
  active: boolean
  upcoming: boolean
  expired: boolean
  excluded: boolean
  finished: boolean
  required_minutes: number
  progress: number
  starts: string
  ends: string
  allowed_channels: string
  category_image_url: string
  link_url: string
  drops: Drop[]
}

export type Channel = {
  iid: string
  name: string
  status: string
  game: string
  viewers: string
  drops: boolean
  acl_based: boolean
  watching: boolean
}

export type Settings = {
  priority: string[]
  exclude: string[]
  available_games: string[]
  priority_mode: string
  priority_modes: string[]
  farm_unlinked: boolean
  enable_badges_emotes: boolean
  available_drops_check: boolean
  proxy: string
  language: string
  languages: string[]
  connection_quality: number
}

export type MinerState = {
  status: string
  icon_state: string
  miner: { running: boolean; last_error: string }
  login: { status: string; user_id: string; activation_url: string; user_code: string }
  current_drop: {
    campaign?: string
    game?: string
    rewards?: string
    drop_progress?: number
    campaign_progress?: number
    drop_percent?: string
    campaign_percent?: string
    remaining?: string
    category_image_url?: string
    benefits?: Benefit[]
  }
  channels: Channel[]
  campaigns: Campaign[]
  websockets: { index: number; status: string; topics: number }[]
  settings: Partial<Settings>
  selected_channel_id: string | null
  logs: string[]
}
