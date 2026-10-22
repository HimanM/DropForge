import assert from "node:assert/strict"
import { test } from "node:test"
import { filterLogs } from "../src/lib/logs.ts"

test("newest entries are first without reversing multiline errors or mutating the source", () => {
  const logs = ["12:00:00: Watching: streamer", "12:01:00: Fatal error\nTraceback\nValueError: bad"]
  const visible = filterLogs(logs, "All", "")
  assert.equal(visible[0].message, logs[1])
  assert.equal(visible[1].message, logs[0])
  assert.equal(logs[0], "12:00:00: Watching: streamer")
})

test("categories, errors and case-insensitive search work together", () => {
  const logs = ["Free badge completed: WARDOGS", "Twitch token rejected", "Drop claimed: Spray", "Cannot connect to spade.twitch.tv", "Settings lists saved."]
  assert.deepEqual(filterLogs(logs, "Badges", "wardogs").map((entry) => entry.message), [logs[0]])
  assert.equal(filterLogs(logs, "Authentication", "")[0].message, logs[1])
  assert.equal(filterLogs(logs, "Drops", "")[0].message, logs[2])
  assert.equal(filterLogs(logs, "Network", "")[0].message, logs[3])
  assert.equal(filterLogs(logs, "Settings", "")[0].message, logs[4])
  assert.equal(filterLogs(logs, "Errors", "").length, 2)
  assert.equal(filterLogs(logs, "Errors", "TOKEN").length, 1)
  assert.deepEqual(filterLogs(logs, "Badges", "missing"), [])
})
