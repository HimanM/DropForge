from __future__ import annotations

from dataclasses import dataclass, field


def clamp_progress(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def format_percent(value: float) -> str:
    return f"{clamp_progress(value):.1%}"


@dataclass(slots=True)
class DropSnapshot:
    campaign: str = "..."
    game: str = "..."
    rewards: str = "..."
    drop_progress: float = 0.0
    campaign_progress: float = 0.0
    remaining: str = "--:--:--"

    @property
    def drop_percent(self) -> str:
        return format_percent(self.drop_progress)

    @property
    def campaign_percent(self) -> str:
        return format_percent(self.campaign_progress)


@dataclass(slots=True)
class CampaignFilters:
    show_not_linked: bool = True
    show_upcoming: bool = True
    show_expired: bool = False
    show_excluded: bool = False
    show_finished: bool = False


@dataclass(slots=True)
class CampaignSnapshot:
    id: str
    name: str
    game: str
    status: str
    linked: bool
    active: bool
    upcoming: bool
    expired: bool
    excluded: bool
    finished: bool
    required_minutes: int
    progress: float
    drops: tuple[str, ...]
    starts: str
    ends: str
    allowed_channels: str

    @property
    def percent(self) -> str:
        return format_percent(self.progress)


@dataclass(slots=True)
class ChannelSnapshot:
    iid: str
    name: str
    status: str
    game: str
    viewers: str
    drops: bool
    acl_based: bool
    watching: bool = False

    @property
    def row(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.name,
            self.status,
            self.game,
            "yes" if self.drops else "no",
            self.viewers,
            "yes" if self.acl_based else "no",
        )


@dataclass(slots=True)
class WebsocketSnapshot:
    index: int
    status: str = "Disconnected"
    topics: int = 0


@dataclass(slots=True)
class LoginSnapshot:
    status: str = "Logged out"
    user_id: str = "-"
    activation_url: str = ""
    user_code: str = ""


@dataclass(slots=True)
class TUIState:
    status: str = "Starting"
    icon_state: str = "pickaxe"
    settings_text: str = ""
    priority: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    available_games: list[str] = field(default_factory=list)
    priority_mode: str = "Priority list only"
    farm_unlinked: bool = False
    campaign_filters: CampaignFilters = field(default_factory=CampaignFilters)
    login: LoginSnapshot = field(default_factory=LoginSnapshot)
    current_drop: DropSnapshot = field(default_factory=DropSnapshot)
    channels: dict[str, ChannelSnapshot] = field(default_factory=dict)
    campaigns: dict[str, CampaignSnapshot] = field(default_factory=dict)
    websockets: dict[int, WebsocketSnapshot] = field(default_factory=dict)
    logs: list[str] = field(default_factory=list)

    def add_log(self, message: str) -> None:
        self.logs.append(message)
        del self.logs[:-500]

    def set_drop(self, drop: DropSnapshot | None) -> None:
        self.current_drop = drop or DropSnapshot()
