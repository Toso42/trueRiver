# Video Series Model

## Goal

Define a sane model for episodic video content in `trueRiver` without collapsing seasons and episodes into free-form tags.

## Core rule

Use tags for classification.
Use structured metadata for series hierarchy.

That means:

- classification tags:
  - `Movie`
  - `TV Series`
  - future curatorial tags

- structured episodic metadata:
  - `SeriesTitle`
  - `SeasonNumber`
  - `EpisodeNumber`
  - `EpisodeTitle`
  - `AbsoluteEpisodeNumber` (optional)

## Explicit non-goal

Do not model these as free-form tags:

- `Season 1`
- `Season 2`
- `Episode 3`

That would break:
- stable ordering
- season grouping
- specials handling
- future series UI

## Current implementation status

Implemented now:
- default metadata registry includes:
  - `SeriesTitle`
  - `SeasonNumber`
  - `EpisodeNumber`
  - `EpisodeTitle`
  - `AbsoluteEpisodeNumber`
- normalization rules map common incoming names such as:
  - `SHOW`
  - `TVSHOW`
  - `SEASON`
  - `EPISODE`
  - `EPISODETITLE`
- track/video API payload now exposes:
  - `series_title`
  - `season_number`
  - `episode_number`
  - `episode_title`
  - `absolute_episode_number`

## Classification model

Recommended content split:

### Movie

- tag: `Movie`
- no series metadata required

### TV Series episode

- tag: `TV Series`
- metadata:
  - `SeriesTitle`
  - `SeasonNumber`
  - `EpisodeNumber`
  - `EpisodeTitle`

## Browser organization plan

### First useful phase

Use the existing `/audio/videos` data and group client-side by:
1. `series_title`
2. `season_number`
3. `episode_number`

That gives:
- series list
- series detail
- season switcher
- ordered episode list

### Browser display target

- `Movies`
  - flat browsing

- `TV Series`
  - series cards
  - open series
  - season selector
  - episodes ordered by season/episode

## TV display plan

### Landing

Keep TV landing focused on:
- `Recently Added`
- `All Videos`
- curated rails

Series browsing should be a dedicated drill-down, not a tag hack.

### Series detail surface

Target shape:
- hero / cover
- series metadata
- season selector
- episodes list

## Medium-term backend direction

The metadata-based approach is the correct first step.

If the feature becomes central, the next structural promotion is:
- `VideoSeries`
- `VideoSeason`

But that should happen only after the metadata-driven browsing has proven the UX and grouping rules.

## Immediate next implementation steps

1. expose episodic metadata in browser video cards and detail views
2. add a browser `TV Series` view grouped by `series_title`
3. add season drill-down in TV web mode
4. later mirror the same structure in Android TV native
