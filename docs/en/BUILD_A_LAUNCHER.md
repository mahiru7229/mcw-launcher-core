# Blueprint for Building a Launcher with MCW Core

## Recommended architecture

```text
View → Controller → Task Runner → MCW Core → Result/Exception/Progress → Presenter → View
```

Views should not import provider clients, databases or filesystem implementation details.

## Composition root

Create one `MCWCore` for one application data root and a bounded worker pool. Keep the core object in application services, not as a global widget dependency.

## Task runner

A production task runner should provide unique task IDs, duplicate prevention, blocking/non-blocking policy, started/succeeded/failed/settled events, thread cleanup and cancellation integration.

## Controllers

- Instance controller: list, selection, create, loader, import/export, health, icon and lifecycle.
- Launch controller: selected identity, `LaunchRequest`, progress bridge, result, `on_exit`, pause/resume/cancel.
- Provider controllers: search, details, versions and installation as separate actions.

## Launch state machine

Use an enum-backed state machine rather than button text. Suggested states: idle, starting, paused, cancelling, running, failed and finished.

## First Run Setup

Use Java scan, memory policy and GPU detection from core. Run hardware/network scans on a worker. Persist normalized settings through `LauncherSettingsManager`.

## Modpack flows

Keep Browse Online and Import Provider Package separate. Both should use preview → settings review → import/create. Clearly explain deferred download on first launch.

## Manual download UX

Show provider, project, expected file name and size, official URL and reason. Verify selected files by strong hash/size. Never offer a “skip verification” shortcut.

## Crash and recovery

Use `on_exit` to update badges and expose log/crash-report paths. Bootstrap and startup recovery should reconcile process sessions, operation journals and partial downloads.

## Security

Never log tokens, trust unvalidated archive paths, render unsanitized provider HTML, accept mismatched hashes, or redistribute content without permission.

## Testing

Test controllers with fake cores, provider clients with mocked HTTP, filesystem workflows in temporary roots, and use behavioral tests. Run Windows smoke tests for Java, process supervision, update and DPI behavior.
