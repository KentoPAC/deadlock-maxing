---
name: videos
description: Extract and store tips from a Deadlock YouTube video with DeadlockMax (creator counters, hero guide videos, recommended builds), with timestamps, and use them in hero pages. Use when the user shares or mentions a YouTube video about Deadlock, a creator's guide or tier / role / counter video.
---

# DeadlockMax: creator videos

`P` = the DeadlockMax plugin folder (`.claude/skills/deadlockmax`). Working folders in the project:
`builds/<id>` for a single build, `builds/search-<hero>` for a search.

Opinions are not statistics: date them, cite them with a timestamp, and flag when the measured data disagree.

- **videos.py**: creator YouTube tips (`fetch <url>` = subtitles via yt-dlp split by chapter; `add <id> -` =
  tips per hero with `"text"` (French) and `"en"`, English hero / item names converted to ids; fields left out keep
  their saved value; `guide <id> <hero> <build_id>@<mm:ss>` = the video is a guide for that hero and recommends that
  build; `list`). A hero guide video is the best source for `plan.lane` and the phase texts (cite
  `video:<id>@<s>`); when the user mentions one, find it and use it. Data in `data/videos.json`, tips shown in
  "Le contrer" ("L'avis des créateurs") with a timestamped link, the date, ⚠ when older than the last big patch, and
  ✓ when a quoted item also stands out in the stats. An opinion is not a statistic: flag disagreements. Adding a
  video = a changelog entry when it changes the method.
  Reference: AndrewChicken, "1 Counter For EVERY Deadlock Hero" (C3yn9SdVHZ8); "Counter Buying…" (Zb82rYYumbY),
  kept for the future live optimisation module (counter-buying during a game).
  Guides: Paz, "The BEST Comprehensive Guide to VIOLET" (kW6zL2_22X4), recommends oses's build 897240.
  Subtitles: only the original track is fetched (`en-orig`); asking for every translated track gets a 429.
