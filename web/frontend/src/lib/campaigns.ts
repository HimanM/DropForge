import type { Campaign } from "../types"

export type CampaignFilter = "available" | "all" | "finished"
export type RewardFilter = "all" | "free-badges"

export function filterCampaigns(campaigns: Campaign[], filter: CampaignFilter, rewards: RewardFilter, query: string): Campaign[] {
  const freeBadges = rewards === "free-badges"
  return campaigns.flatMap((campaign) => {
    if (!`${campaign.game} ${campaign.name}`.toLowerCase().includes(query.toLowerCase())) return []
    const drops = freeBadges ? campaign.drops.filter((drop) => drop.is_free_badge && drop.required_minutes > 0) : campaign.drops
    if (!drops.length) return []
    const finished = freeBadges ? drops.every((drop) => drop.claimed || drop.earned) : campaign.finished
    if (filter === "finished" && !finished) return []
    // The badge browser includes non-priority categories without changing mining rules.
    if (filter === "available" && (finished || campaign.expired || !freeBadges && campaign.excluded)) return []
    return freeBadges ? [{ ...campaign, drops, finished, status: finished ? "Finished" : campaign.status,
      progress: drops.reduce((sum, drop) => sum + (drop.claimed || drop.earned ? 1 : drop.progress), 0) / drops.length,
    }] : [campaign]
  })
}
