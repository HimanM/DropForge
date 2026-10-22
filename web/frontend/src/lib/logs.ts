export const logCategories = ["Drops", "Badges", "Authentication", "Network", "Mining", "Settings", "Other"] as const
export type LogFilter = "All" | "Errors" | typeof logCategories[number]

export function filterLogs(logs: string[], filter: LogFilter, query: string) {
  return logs.map((message, index) => {
    // Engine logs are text, so categories are best-effort; the original message is retained.
    const category = /settings|priority mode|set to (?:true|false)|saved.*lists/i.test(message) ? "Settings"
      : /auth|login|log in|oauth|token|activation|integrity|verification|credentials/i.test(message) ? "Authentication"
      : /badge/i.test(message) ? "Badges"
      : /claim|drop.*(?:earned|complete|progress)|reward|inventory|campaign|catalogue/i.test(message) ? "Drops"
      : /connect|network|websocket|timeout|timed out|spade|https?:\/\/|retrying/i.test(message) ? "Network"
      : /watching|miner|farming|channel|priority work|idle/i.test(message) ? "Mining" : "Other"
    const error = /\berror\b|fatal|traceback|exception|failed|failure|cannot|rejected|unavailable/i.test(message)
    return { message, index, category, error }
  }).filter((entry) => (filter === "All" || (filter === "Errors" ? entry.error : entry.category === filter))
    && entry.message.toLowerCase().includes(query.toLowerCase())).reverse()
}
