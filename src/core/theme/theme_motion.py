from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MotionTransitionDefinition:
    transition_type: str = "fade"
    duration_ms: int = 160
    easing: str = "out_cubic"
    distance_px: int = 20


@dataclass(frozen=True)
class ButtonMotionDefinition:
    hover_duration_ms: int = 100
    press_duration_ms: int = 70
    easing: str = "out_quad"
    hover_strength: float = 0.08
    press_strength: float = 0.18


@dataclass(frozen=True)
class SidebarMotionDefinition:
    duration_ms: int = 220
    easing: str = "out_cubic"
    collapsed_width: int = 72


@dataclass(frozen=True)
class ToastMotionDefinition:
    transition_type: str = "slide_fade"
    duration_ms: int = 180
    visible_duration_ms: int = 3000
    easing: str = "out_cubic"
    distance_px: int = 24
    max_visible: int = 3


@dataclass(frozen=True)
class MotionPerformanceDefinition:
    full_fps: int = 60
    reduced_fps: int = 30
    pause_when_hidden: bool = True


@dataclass(frozen=True)
class ThemeMotionDefinition:
    page: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition("fade_slide", 170, "out_cubic", 18))
    dialog: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition("fade", 160, "out_cubic", 12))
    launch_control: MotionTransitionDefinition = field(default_factory=lambda: MotionTransitionDefinition("fade", 140, "out_cubic", 8))
    button: ButtonMotionDefinition = field(default_factory=ButtonMotionDefinition)
    sidebar: SidebarMotionDefinition = field(default_factory=SidebarMotionDefinition)
    toast: ToastMotionDefinition = field(default_factory=ToastMotionDefinition)
    performance: MotionPerformanceDefinition = field(default_factory=MotionPerformanceDefinition)
