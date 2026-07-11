package io.github.himanm.tdminer

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class TwitchGqlTest {
    @Test
    fun parsesInventorySnapshot() {
        val snapshot = parseInventorySnapshot(
            """
            {
              "data": {
                "currentUser": {
                  "inventory": {
                    "dropCampaignsInProgress": [{
                      "name": "Detroit Badge Drop",
                      "game": {"displayName": "Detroit: Become Human"},
                      "timeBasedDrops": [{
                        "name": "Android Triangle",
                        "requiredMinutesWatched": 60,
                        "self": {"currentMinutesWatched": 15, "isClaimed": false},
                        "benefitEdges": [{"benefit": {"name": "Triangle"}}]
                      }]
                    }]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertNotNull(snapshot)
        assertEquals("Detroit: Become Human", snapshot!!.game)
        assertEquals("Detroit Badge Drop", snapshot.campaign)
        assertEquals("Android Triangle", snapshot.drop)
        assertEquals("00:45:00", snapshot.remaining)
        assertEquals(0.25f, snapshot.dropProgress)
    }

    @Test
    fun parsesInventorySnapshotGameNameFallback() {
        val snapshot = parseInventorySnapshot(
            """
            {
              "data": {
                "currentUser": {
                  "inventory": {
                    "dropCampaignsInProgress": [{
                      "name": "OWCS S2 Campaign 3",
                      "game": {"name": "Overwatch 2"},
                      "timeBasedDrops": [{
                        "name": "Battle Pass Tier Skip",
                        "requiredMinutesWatched": 180,
                        "self": {"currentMinutesWatched": 4, "isClaimed": false}
                      }]
                    }]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals("Overwatch 2", snapshot!!.game)
    }

    @Test
    fun skipsSubOnlyDropsButKeepsTimedDropInSameCategory() {
        val snapshot = parseInventorySnapshot(
            """
            {
              "data": {
                "currentUser": {
                  "inventory": {
                    "dropCampaignsInProgress": [{
                      "name": "Mixed Campaign",
                      "game": {"displayName": "Example Game"},
                      "timeBasedDrops": [
                        {
                          "name": "Sub-only reward",
                          "requiredMinutesWatched": 0,
                          "self": {"currentMinutesWatched": 0, "isClaimed": false}
                        },
                        {
                          "name": "Timed reward",
                          "requiredMinutesWatched": 60,
                          "self": {"currentMinutesWatched": 12, "isClaimed": false}
                        }
                      ]
                    }]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals("Example Game", snapshot!!.game)
        assertEquals("Timed reward", snapshot.drop)
    }

    @Test
    fun skipsExpiredInventoryCampaigns() {
        val snapshots = parseInventorySnapshots(
            """
            {
              "data": {
                "currentUser": {
                  "inventory": {
                    "dropCampaignsInProgress": [
                      {
                        "name": "Expired OWCS",
                        "status": "EXPIRED",
                        "startAt": "2020-01-01T00:00:00Z",
                        "endAt": "2020-02-01T00:00:00Z",
                        "game": {"displayName": "Overwatch"},
                        "timeBasedDrops": [{
                          "name": "Old Reward",
                          "requiredMinutesWatched": 60,
                          "self": {"currentMinutesWatched": 1, "isClaimed": false}
                        }]
                      },
                      {
                        "name": "Active OWCS",
                        "status": "ACTIVE",
                        "startAt": "2020-01-01T00:00:00Z",
                        "endAt": "2099-02-01T00:00:00Z",
                        "game": {"displayName": "Overwatch"},
                        "timeBasedDrops": [{
                          "name": "Live Reward",
                          "requiredMinutesWatched": 60,
                          "self": {"currentMinutesWatched": 1, "isClaimed": false}
                        }]
                      }
                    ]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals(1, snapshots.size)
        assertEquals("Active OWCS", snapshots[0].campaign)
    }

    @Test
    fun priorityWithoutTimedDropFallsThroughToNextPriority() {
        val selected = selectInventorySnapshot(
            listOf(
                TwitchDropSnapshot(
                    game = "Second",
                    campaign = "Timed",
                    drop = "Reward",
                    currentMinutes = 1,
                    requiredMinutes = 30,
                    campaignProgress = 0.1f,
                ),
            ),
            priorityGames = listOf("First", "Second"),
            excludedGames = emptyList(),
        )

        assertEquals("Second", selected!!.game)
    }

    @Test
    fun samePriorityGameSelectsCampaignWithLowestRemainingTime() {
        val selected = selectInventorySnapshot(
            listOf(
                TwitchDropSnapshot(
                    game = "Overwatch",
                    campaign = "Long Campaign",
                    drop = "Long Reward",
                    currentMinutes = 0,
                    requiredMinutes = 120,
                    campaignProgress = 0f,
                ),
                TwitchDropSnapshot(
                    game = "Overwatch",
                    campaign = "Short Campaign",
                    drop = "Short Reward",
                    currentMinutes = 25,
                    requiredMinutes = 30,
                    campaignProgress = 0.5f,
                ),
            ),
            priorityGames = listOf("Overwatch"),
            excludedGames = emptyList(),
        )

        assertEquals("Short Campaign", selected!!.campaign)
    }

    @Test
    fun completedDropIsDisplayedAfterAndNeverSelectedOverUnfinishedDrop() {
        val completed = TwitchDropSnapshot(
            game = "Rust", campaign = "Charity", drop = "Bed",
            currentMinutes = 120, requiredMinutes = 120, campaignProgress = 0.75f,
        )
        val unfinished = TwitchDropSnapshot(
            game = "Rust", campaign = "Charity", drop = "Furnace",
            currentMinutes = 0, requiredMinutes = 120, campaignProgress = 0.75f,
        )

        assertEquals("Furnace", selectInventorySnapshot(listOf(completed, unfinished), listOf("Rust"), emptyList())!!.drop)
        assertEquals(listOf("Furnace", "Bed"), filterPrioritySnapshots(listOf(completed, unfinished), listOf("Rust"), emptyList()).map { it.drop })
    }

    @Test
    fun noPrioritySelectsNothing() {
        val selected = selectInventorySnapshot(
            listOf(
                TwitchDropSnapshot(
                    game = "First",
                    campaign = "Long",
                    drop = "Reward",
                    currentMinutes = 0,
                    requiredMinutes = 60,
                    campaignProgress = 0f,
                ),
                TwitchDropSnapshot(
                    game = "Second",
                    campaign = "Short",
                    drop = "Reward",
                    currentMinutes = 58,
                    requiredMinutes = 60,
                    campaignProgress = 0.9f,
                ),
            ),
            priorityGames = emptyList(),
            excludedGames = emptyList(),
        )

        assertEquals(null, selected)
    }

    @Test
    fun filtersDisplayDropsToPriorityGames() {
        val drops = filterPrioritySnapshots(
            listOf(
                TwitchDropSnapshot(
                    game = "Detroit: Become Human",
                    campaign = "Detroit Badge Drop",
                    drop = "Android Triangle",
                    currentMinutes = 1,
                    requiredMinutes = 60,
                    campaignProgress = 0.01f,
                ),
                TwitchDropSnapshot(
                    game = "Overwatch",
                    campaign = "Long Campaign",
                    drop = "Long Reward",
                    currentMinutes = 0,
                    requiredMinutes = 120,
                    campaignProgress = 0f,
                ),
                TwitchDropSnapshot(
                    game = "Overwatch",
                    campaign = "Short Campaign",
                    drop = "Short Reward",
                    currentMinutes = 25,
                    requiredMinutes = 30,
                    campaignProgress = 0.5f,
                ),
            ),
            priorityGames = listOf("Overwatch"),
            excludedGames = emptyList(),
        )

        assertEquals(2, drops.size)
        assertEquals("Short Campaign", drops[0].campaign)
        assertEquals("Long Campaign", drops[1].campaign)
    }

    @Test
    fun parsesDropCategories() {
        val categories = parseDropCategories(
            """
            {
              "data": {
                "currentUser": {
                  "dropCampaigns": [
                    {"status": "ACTIVE", "game": {"id": "515025", "displayName": "Overwatch 2"}},
                    {"status": "UPCOMING", "game": {"id": "218378525", "displayName": "Marvel Rivals"}},
                    {
                      "status": "EXPIRED",
                      "endAt": "2020-02-01T00:00:00Z",
                      "game": {"id": "old", "displayName": "Expired Game"}
                    }
                  ]
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals("Overwatch 2", categories[0].name)
        assertEquals("218378525", categories[1].id)
        assertEquals(2, categories.size)
    }

    @Test
    fun parsesActiveDropCampaignIds() {
        val ids = parseDropCampaignIds(
            """
            {
              "data": {
                "currentUser": {
                  "dropCampaigns": [
                    {"id": "active-1", "status": "ACTIVE"},
                    {"id": "upcoming-1", "status": "UPCOMING"},
                    {"id": "expired-1", "status": "EXPIRED"}
                  ]
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals(listOf("active-1", "upcoming-1"), ids)
    }

    @Test
    fun parsesCampaignDetailCategories() {
        val categories = parseCampaignDetailCategories(
            """
            {
              "data": {
                "user": {
                  "dropCampaign": {
                    "id": "campaign-1",
                    "game": {"id": "65632", "displayName": "Rust"}
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals(1, categories.size)
        assertEquals("65632", categories[0].id)
        assertEquals("Rust", categories[0].name)
    }

    @Test
    fun parsesCampaignDetailSnapshotWithoutSelfProgress() {
        val snapshots = parseCampaignDetailSnapshots(
            """
            {
              "data": {
                "user": {
                  "dropCampaign": {
                    "id": "campaign-1",
                    "name": "Rust Charity 26 Bed",
                    "status": "ACTIVE",
                    "startAt": "2020-01-01T00:00:00Z",
                    "endAt": "2099-02-01T00:00:00Z",
                    "game": {"id": "263490", "displayName": "Rust"},
                    "timeBasedDrops": [{
                      "name": "Rust Charity '26 Bed",
                      "requiredMinutesWatched": 120,
                      "benefitEdges": [{"benefit": {"name": "Rust Charity '26 Bed"}}]
                    }]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals(1, snapshots.size)
        assertEquals("Rust", snapshots[0].game)
        assertEquals("Rust Charity 26 Bed", snapshots[0].campaign)
        assertEquals("02:00:00", snapshots[0].remaining)
    }

    @Test
    fun snapshotDropKeyUsesCampaignAndDropIds() {
        val first = TwitchDropSnapshot(
            campaignId = "campaign-1",
            dropId = "drop-1",
            game = "Rust",
            campaign = "Same Name",
            drop = "Same Drop",
            currentMinutes = 0,
            requiredMinutes = 60,
            campaignProgress = 0f,
        )
        val duplicate = first.copy(currentMinutes = 10)

        assertEquals(1, listOf(first, duplicate).distinctBy { it.dropKey }.size)
    }

    @Test
    fun parsesInventoryCategories() {
        val categories = parseInventoryCategories(
            """
            {
              "data": {
                "currentUser": {
                  "inventory": {
                    "dropCampaignsInProgress": [
                      {"game": {"id": "123", "displayName": "Battlefield 6"}},
                      {
                        "status": "EXPIRED",
                        "endAt": "2020-02-01T00:00:00Z",
                        "game": {"id": "old", "displayName": "Expired Inventory Game"}
                      }
                    ]
                  }
                }
              }
            }
            """.trimIndent(),
        )

        assertEquals("Battlefield 6", categories[0].name)
        assertEquals(1, categories.size)
    }

    @Test
    fun gameEventBenefitClaimPreventsRefarmingDropWithoutSelfEdge() {
        val snapshots = parseInventorySnapshots(
            """
            {"data":{"currentUser":{"inventory":{
              "gameEventDrops":[{"id":"benefit-1","lastAwardedAt":"2026-07-10T12:00:00Z"}],
              "dropCampaignsInProgress":[{
                "id":"campaign-1","name":"Overwatch","status":"ACTIVE",
                "startAt":"2026-07-01T00:00:00Z","endAt":"2026-08-01T00:00:00Z",
                "game":{"id":"515025","displayName":"Overwatch"},
                "timeBasedDrops":[{
                  "id":"drop-1","name":"Captured Moments Player Icon",
                  "startAt":"2026-07-01T00:00:00Z","endAt":"2026-08-01T00:00:00Z",
                  "requiredMinutesWatched":60,
                  "benefitEdges":[{"benefit":{"id":"benefit-1","name":"Captured Moments Player Icon"}}]
                }]
              }]
            }}}}
            """.trimIndent(),
        )

        assertEquals(0, snapshots.size)
    }

    @Test
    fun parsesGameRedirectSlug() {
        val slug = parseGameSlug("""{"data":{"game":{"slug":"overwatch-2"}}}""")

        assertEquals("overwatch-2", slug)
    }
}
