import assert from "node:assert/strict"
import { test } from "node:test"
import { filterCampaigns } from "../src/lib/campaigns.ts"
import type { Campaign, Drop } from "../src/types.ts"

const badge = { id: "watch", is_free_badge: true, required_minutes: 60, progress: 0.5, claimed: false, earned: false } as Drop
const mixed = { id: "campaign", game: "Badge Game", name: "Mixed rewards", excluded: true, expired: false, finished: false, progress: 0.1,
  drops: [badge, { ...badge, id: "sub", required_minutes: 0, is_free_badge: false }, { ...badge, id: "item", is_free_badge: false }],
} as Campaign

test("free badges include non-priority categories but exclude subscriptions and items", () => {
  const [campaign] = filterCampaigns([mixed], "available", "free-badges", "badge")
  assert.deepEqual(campaign.drops.map((drop) => drop.id), ["watch"])
  assert.equal(campaign.progress, 0.5)
  assert.equal(mixed.drops.length, 3)
  assert.deepEqual(filterCampaigns([mixed], "available", "all", ""), [])
})

test("a badge earned in a mixed campaign is finished regardless of the remaining items", () => {
  const completed = { ...mixed, drops: [{ ...badge, claimed: true }, mixed.drops[2]] }
  assert.deepEqual(filterCampaigns([completed], "available", "free-badges", ""), [])
  const [campaign] = filterCampaigns([completed], "finished", "free-badges", "")
  assert.equal(campaign.finished, true)
  assert.equal(campaign.progress, 1)
  assert.equal(campaign.status, "Finished")
})

test("zero-time badges never qualify, even if a server mislabels them", () => {
  const subscription = { ...mixed, drops: [{ ...badge, required_minutes: 0 }] }
  assert.deepEqual(filterCampaigns([subscription], "all", "free-badges", ""), [])
})

test("search and expiry still apply to the free badge browser", () => {
  assert.deepEqual(filterCampaigns([mixed], "all", "free-badges", "missing"), [])
  assert.deepEqual(filterCampaigns([{ ...mixed, expired: true }], "available", "free-badges", ""), [])
  assert.equal(filterCampaigns([{ ...mixed, expired: true }], "all", "free-badges", "").length, 1)
})
