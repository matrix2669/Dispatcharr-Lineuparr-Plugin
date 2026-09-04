# Lineuparr user guide

Everything needed to configure and run Lineuparr, in the order you will need it.
Newer to the plugin? Read [the project front page](../README.md) first for what
it does and how to install it.

| Also available | |
|---|---|
| [Project front page](../README.md) | what the plugin is, the lineups it ships, and installation |
| [Lineup file format](LINEUP-FORMAT.md) | writing or contributing your own lineup |

---

## Contents

- [The short version](#the-short-version)
- [Settings reference](#settings-reference)
- [Match sensitivity](#match-sensitivity)
- [Step by step](#step-by-step)
- [The actions, one by one](#the-actions-one-by-one)
- [Unmatched channel cleanup](#unmatched-channel-cleanup)
- [Custom aliases](#custom-aliases)
- [Country matching](#country-matching)
- [IPTV Checker integration](#iptv-checker-integration)
- [Troubleshooting](#troubleshooting)
- [How matching works](#how-matching-works)
- [Reports](#reports)
- [File locations](#file-locations)

---

## The short version

1. Pick a **Lineup File** and an **M3U Source**, then save.
2. Run **Validate Settings**. It reports the lineup summary and catches a bad
   configuration before anything is created.
3. Run **Preview Stream Match**. Nothing is changed; a CSV lands in
   `/data/exports/` showing what would match, with a confidence score per channel.
4. If the preview looks right, run **Full Sync**.

Steps 2 and 3 are optional and worth doing anyway. A preview costs nothing and
tells you whether your match sensitivity is set sensibly for your source.

---

## Generated lineups from GraceNoteScraper

If GraceNoteScraper is building the lineup, Lineuparr can keep its own persistent copy without a plugin reinstall:

1. Paste the GraceNoteScraper export endpoint into **Generated Lineup URL** and save the settings. For example, `http://gracenotescraper:8080/api/lineuparr/export` when both containers share a Docker network.
2. Select **Lineup from URL** once, then run **Import / Refresh Generated Lineup**. Dispatcharr saves the panel settings before running the action; no separate Save is needed.
3. Proceed to Preview without toggling the plugin. **Lineup from URL** resolves the latest successful import for each action and uses **Exact** internally regardless of the sensitivity dropdown. Failed downloads or validation leave the prior import available. Before the first successful import, lineup actions fail clearly rather than falling back. Older imports appear individually after reloading the plugin. Selecting an individual or built-in lineup uses its normal sensitivity setting.
4. Run **Validate Settings** before syncing.

The action accepts HTTP or HTTPS, validates the JSON before replacing anything, and writes it atomically under `/data/lineuparr/lineups`. Its result identifies an empty or unreachable URL, or reports **Created new lineup file** or **Refreshed lineup file** with the exact filename. Running it again with the same generated filename recreates that file with the newest response and clears Lineuparr's in-memory lineup cache. If the generated filename is different, it is saved as another persistent lineup; existing lineup files are never deleted by this action.

The server must provide a filename in the form `{CC}_{Provider}_lineup.json`, either through the HTTP `Content-Disposition` header or at the end of the URL. GraceNoteScraper's export endpoint already supplies this header. The country code is required for Lineuparr's country filtering and logo lookup. Do not put credentials in the URL; Lineuparr rejects URLs containing a username or password.

---

## Settings reference

| Setting | Type | Default | What it does |
|---------|------|---------|--------------|
| Generated Lineup URL | string | *(empty)* | HTTP or HTTPS endpoint whose JSON is saved by the Import / Refresh Generated Lineup action. |
| Lineup File | select | `US_DirecTV-Premier_lineup.json` | The provider lineup to mirror. The list includes built-in files and persistent files under `/data/lineuparr/lineups`. |
| M3U Source | select | *(empty)* | Which M3U account's streams to match against. Leave unset to use every active source. |
| Channel Profile | select | *(empty)* | Channel profile that synced channels are enabled in. |
| Channel Group Prefix | string | *(empty)* | Prefix added to the channel group names the plugin creates. |
| Category Detail | select | `Normal` | How lineup categories are grouped: None, Refined, Simple or Normal. |
| Match Sensitivity | select | `Normal` | Matching strictness. See [Match sensitivity](#match-sensitivity). |
| Channel Numbering | select | `Use Channel Database Numbers` | Database numbers, auto-assign next, auto-assign after highest, or start from a specific number. |
| Starting Channel Number | string | *(empty)* | Only used by the "specific number" mode. |
| Order Matched Streams by Quality | boolean | `true` | Sorts the streams attached to a channel, 4K before HD before SD. Changes ordering only, never which streams attach. |
| Preserve Existing Streams | boolean | `false` | Appends newly matched streams instead of replacing them, skips duplicates, and keeps channels that matched nothing. Use this when a second source already populates the same channels. |
| Single Channel Match | string | *(empty)* | Scopes Preview Stream Match, Apply Stream Match, Apply EPG Match and Assign Logos to the one lineup channel with this exact name, case-insensitive. Full Sync ignores it. |
| Rate Limiting | select | `None` | Throttles between operations: None, Low, Medium or High. Use it if a large sync makes Dispatcharr sluggish. |
| Custom Channel Aliases (JSON) | string | *(empty)* | Your own alias overrides. See [Custom aliases](#custom-aliases). |
| EPG Sources | select | `All EPG sources` | Which EPG source or sources to match against. "All" uses every source in the priority order configured in Dispatcharr. |
| Send reports to Newsflasharr | boolean | `false` | Master switch for emailing reports. When off, reports are still written to disk and nothing is sent. See [Reports](#reports). |
| When to send | select | `Never` | Never, or after every run that produces a report. |
| What to attach | select | `Both the HTML page and the CSV` | Which report files are emailed. Both means two emails, because one notification carries one attachment. |

---

## Match sensitivity

| Level | Best for |
|-------|----------|
| Relaxed | Maximum coverage. Cast a wide net, then review the CSV for false positives. |
| Normal | General use. Good accuracy with reasonable coverage. |
| Strict | High-confidence matches only. Fewer results, fewer mistakes. |
| Exact | Near-exact matches only. Minimal false positives, will miss some valid matches. |

### Noisy or multi-country sources

Lineuparr attaches every stream at or above the threshold to a channel, so the
channel has failover options. A large multi-country playlist can therefore
attach a sibling-but-different feed that shares a common word: a US "Fox Sports
1" picking up "TNT Sports 1", "Sky Sports F1" or "AFN Sports", or "Sports Mix"
picking up "Sky Sports Mix". Those land in the 81 to 89 percent range, so
**Strict** removes them while keeping the genuine matches.

If Strict still lets a few through, there are two more levers. Matching only
ever reads the stream **name**, never its channel group, so:

- **Limit the M3U Source.** The cleanest fix. If the foreign feeds come from a
  different M3U account than the channels you want, do not select that source
  for the run. Those streams never enter the candidate pool at any sensitivity.
  Sorting streams into country-named *groups* does not help, because the matcher
  does not read group names.
- **Prefix the stream name with a country code.** A stream whose name carries a
  recognized country marker different from the lineup's country is dropped:
  `UK: Sky Sports F1`, `UK| Sky Sports`, `UK Sky Sports` or `(UK) Sky Sports`.
  Bulk-renaming the offending streams makes them drop out of a US lineup
  automatically. One exception: a bare `IN ` prefix is not read as India,
  because it collides with the English word "in" (the real channel "In Country
  Television"), so use `(IN)` or `IN:` for Indian feeds.

---

## Step by step

**1. Configure.** Select the Lineup File and M3U Source, optionally set a
Channel Group Prefix and Channel Profile, choose a Match Sensitivity, and save.

**2. Validate Settings.** Verifies the lineup file and the M3U source, and
reports channel counts per category. It also warns when the channel group prefix
or the EPG source filter names a different country from the lineup, and when an
EPG source it would match against is switched off in Dispatcharr. Recommended.

**3. Preview Stream Match.** A dry run. Shows what would match, with a
confidence score, and writes a CSV to `/data/exports/`. Nothing is changed, so
this is safe at any time. Recommended.

**4. Full Sync.** Creates channel groups from the lineup categories, creates the
channels with the right numbers, matches streams, assigns EPG data, assigns
logos, enables the channels in the selected profile, and removes channels that
matched no streams. See [Unmatched channel cleanup](#unmatched-channel-cleanup).

---

## The actions, one by one

Run these individually when you want more control than Full Sync gives. They all
live on the Actions tab of the plugin panel:

![The top of the Lineuparr Actions tab, showing Validate Settings, Show Status, Preview Stream Match, Full Sync and Sync Channels Only](screenshots/actions-panel-top.jpg)

![The rest of the Actions tab, showing Apply Stream Match Only, Apply EPG Match, Assign Logos, Re-sort Streams by Quality, Clear CSV Exports and Email Report Now](screenshots/actions-panel-bottom.jpg)

| Action | What it does |
|---|---|
| **Import / Refresh Generated Lineup** | Downloads and validates the saved Generated Lineup URL, then reports whether the named persistent JSON file was created or refreshed. |
| **Show Status** | Live progress of the running operation, or the result of the last one, without opening the container logs. |
| **Validate Settings** | Checks the lineup file and M3U source and summarizes the lineup. |
| **Preview Stream Match** | Dry run with a CSV export. Changes nothing. |
| **Full Sync** | The whole pipeline in one click. |
| **Sync Channels Only** | Creates and updates groups and channels from the lineup. No stream matching. |
| **Apply Stream Match Only** | Attaches matched streams to channels that already exist, in quality order. |
| **Apply EPG Match** | Matches EPG entries to channels and assigns the programme guides. |
| **Assign Logos** | Assigns channel logos from EPG icons, the Logo Manager, or the tv-logos repository on GitHub. |
| **Re-sort Streams by Quality** | Re-orders already-attached streams using the newest quality data. See [IPTV Checker integration](#iptv-checker-integration). |
| **Clear CSV Exports** | Deletes the plugin's CSV exports. |
| **Email Report Now** | Sends the newest report already on disk. It does not run a match. See [Reports](#reports). |

**Single Channel Match** scopes Preview Stream Match, Apply Stream Match Only,
Apply EPG Match and Assign Logos to one channel. Full Sync always runs the whole
lineup regardless of that setting.

---

## Unmatched channel cleanup

After stream matching, **Full Sync** and **Apply Stream Match Only** delete any
channel in a Lineuparr-managed group that ended up with zero streams. This keeps
the channel list free of lineup entries your source does not carry.

Two things bound it:

- Only channels in groups Lineuparr created are affected. Your other channels
  are never touched.
- With **Preserve Existing Streams** enabled the cleanup is skipped entirely, so
  a non-destructive add cannot remove channels another source populated.

To see what would go before committing to it, run **Preview Stream Match** and
read the unmatched rows in the CSV.

---

## Custom aliases

An alias is another name your provider uses for a channel. The plugin ships more
than 200 built-in aliases; the **Custom Channel Aliases (JSON)** setting adds
your own on top. Keys are the **exact lineup channel name**, values are the
provider's names for it. A single alias may be a plain string instead of a
one-item list.

```json
{
  "FOX News Channel": ["FOX NEWS HD", "FoxNews", "Fox News USA"],
  "HISTORY Channel, The": ["HISTORY", "History Channel HD", "History US"],
  "My Local Station": ["WABC", "WABC-TV", "ABC 7 New York"]
}
```

**Finding the key.** Open the lineup JSON and copy the `"name"` value exactly. If
the lineup says `"name": "HISTORY Channel, The"`, that whole string is the key.

**Finding the values.** Run **Preview Stream Match** and look at the unmatched
rows in the CSV. The stream names in your own M3U are what to add.

A lineup file can also carry aliases per channel, which is the better home for
variants specific to one provider. See the
[lineup file format](LINEUP-FORMAT.md).

---

## Country matching

A stream whose name carries a country marker that differs from the lineup's own
country is dropped. That is what stops a Canadian feed attaching to a US channel.
Streams with no marker at all are kept, because they cannot be proven wrong and
dropping them would break sources that never tag country.

Some providers do not put a country in the stream name at all. They label by
platform instead, so the same list carries `GO: ESPN`, `RK: VEVO POP` and
`PRIME: SKY NEWS`, and none of those names says where the feed comes from. For
those, the provider group the stream belongs to is read instead, because a group
is normally named for its country, as in `AU| AUSTRALIA VIP` or `US| SPORT`.

Two limits keep that from causing harm. The group is consulted only when the
stream name itself says nothing, so a name that does carry a country is always
judged on the name. And the group is ignored when acting on it would leave a
channel with no candidate streams at all, so a provider whose groups are
mislabelled loses nothing. A stream name appearing under groups of two different
countries is treated as having no country rather than being assigned one.

The lineup's country normally comes from its filename, `US_DirecTV-Premier_lineup.json`
being US. Individual channels can override it, which is how you keep a block of
foreign channels inside an otherwise single-country lineup. Both forms are in the
[lineup file format](LINEUP-FORMAT.md).

---

## IPTV Checker integration

If you also run the
[IPTV Checker plugin](https://github.com/PiratesIRC/Dispatcharr-IPTV-Checker-Plugin),
you can order streams by measured quality rather than by what their names claim:

1. Run **Full Sync** or **Apply Stream Match Only** to attach streams.
2. Run an IPTV Checker scan over the Lineuparr channel groups.
3. Run **Re-sort Streams by Quality**. It uses the resolution and bitrate the
   scan measured instead of the quality words in the stream name.

---

## Troubleshooting

### Start here

Refresh the browser with F5, then restart the container:

```bash
docker restart dispatcharr
```

A surprising share of plugin problems are a stale browser page or a plugin
module still resident in memory from before an update.

### Plugin not found

Refresh the page, then restart the container. Dispatcharr discovers plugins at
worker start and when the Plugins page is opened.

### Low match rate

- Try **Relaxed** while you are finding your feet, then tighten.
- Run **Preview Stream Match** and read the CSV. It names every channel that
  found nothing.
- Add **Custom Aliases** for channels whose provider names differ.
- Confirm the M3U source actually carries the channels you expect.

### Channels created but no streams attached

- Check that the M3U Source setting points at the right account.
- Run **Preview Stream Match** to see the scores.
- If the stream names differ a lot from the lineup names, aliases are the fix.

### EPG not assigned

- Confirm EPG sources are configured in Dispatcharr.
- Run **Apply EPG Match** on its own to get the detailed log.
- Read the logs: `docker logs dispatcharr | grep "Lineuparr"`.

**A brand new EPG source works, and the log will say it is running degraded.**
Dispatcharr downloads programme data only for guide entries that are already
attached to a channel, and attaching them is what Apply EPG Match does, so a
source you have just added always starts with no programme data. Matching runs
against every entry in that case and logs a warning saying so. Once channels are
attached, the refresh that follows fills the programme data in.

**Check whether the source is switched on.** Matching reads guide entries whether
or not their source is enabled, and Dispatcharr never refreshes a disabled
source, so a channel matched to one keeps a guide that quietly stops being
updated. **Validate Settings** lists any source in your filter that is switched
off.

### Progress not updating

Operations run in the background and keep going even if the browser gives up.
Click **Show Status** for live progress and an estimated finish time, or the last
run's summary. The container logs carry the same detail.

---

## How matching works

Each lineup channel goes through four stages, in order, and stops at the first
that produces a confident answer:

1. **Alias match.** The built-in table, the lineup's own per-channel aliases, and
   your custom aliases.
2. **Exact match.** Normalized name comparison with spacing and punctuation
   stripped.
3. **Substring match.** One name contained in the other, with a length-ratio
   check so a short name cannot swallow a long one.
4. **Fuzzy token sort.** Edit distance over sorted, cleaned tokens.

Five guards apply across all four:

- **Length-scaled thresholds.** Shorter names must be more similar to pass, since
  a one-character difference matters more in a five-character name.
- **Token overlap.** A distinctive token has to be shared, which is what stops
  "ABC News" matching "BBC News".
- **Regional filtering.** East, West and Pacific variants only match streams of
  the same region.
- **Callsign anchoring.** A shared high-confidence US broadcast callsign such as
  "WABC" rescues a correct match, and a disagreeing one rejects a false match.
- **Channel number boost.** A three-or-more-digit channel number appearing in the
  stream name breaks ties. Only active in "Use Channel Database Numbers" mode.

---

## Reports

Every action that produces a CSV also writes a shareable report: one HTML page
and one CSV, both named for the moment they were written, in
`/data/lineuparr_reports` inside the container. The eight newest of each are
kept and older ones are deleted.

### What the page looks like

The page opens as an index rather than as one long table. Rows are grouped into
sections that all start collapsed, so you open the one you care about:

| Section | What it holds |
|---|---|
| **Strong matches** | Scored 90 or above. Least likely to need a second look. |
| **Worth checking** | Scored 60 to 89. Good enough to propose, not good enough to trust without reading. This is where your time goes. |
| **Weak or no match** | Scored below 60, or nothing found at all. An alias is usually the fix. See [Custom aliases](#custom-aliases). |

Each heading carries the number of rows in its own table. A report that has no
score column, such as the channel sync preview, groups by status instead.

Every table sorts by clicking a column heading, or by focusing it and pressing
Enter. Sorting needs a browser: a mail client previewing the file shows every
row but cannot reorder them.

The page is one self-contained file with no external images, fonts or scripts,
so it renders the same opened from disk, forwarded as an attachment, or read on
a television browser with no internet connection. It follows your system's light
or dark setting.

### What is left out, deliberately

Stream names in a report have their M3U source label removed, and the plugin
settings that name your M3U sources are not included. On a real installation
that label is your provider's hostname. The complete export, which does include
it, stays in `/data/exports` inside the container and is never emailed.

Reports are deliberately not written to `/data/logos`. Dispatcharr's web server
publishes that directory to your whole local network with no password.

### Emailing reports

Reports are delivered by the separate **Newsflasharr** plugin, which handles the
mail account. Lineuparr never sends mail itself.

Turn on **Send reports to Newsflasharr** in the settings, choose whether to send
on every run or never, and choose the HTML page, the CSV, or both. Sending both
produces two emails, because one notification carries one attachment.

Set up a routing rule in Newsflasharr matching source `lineuparr` and event
`usage_report`, sending to the mail channel. **Mark the rule exclusive.** Without
that, Newsflasharr adds its default channel as well and the report goes to two
places.

**Email Report Now** sends the newest report already on disk. It does not run a
match, because a match takes minutes and the button asks to send a report rather
than to produce one.

### The report count

The plugin writes the number of reports it has built to
`/data/lineuparr/report_count.json`. Newsflasharr's Show Status action reads it
and prints the count next to this plugin. Nothing else uses it.

It counts reports whose files reached the disk, so a run that failed to write
one does not increase it. It is not a delivery count: a report built while
emailing is switched off still counts. The number is a floor rather than an
exact total, because two reports finishing at the same instant can lose a count
between them.

A plugin appears in that Newsflasharr readout only after it has delivered at
least one report through Newsflasharr, whatever the count file says.

---

## File locations

| What | Where |
|---|---|
| CSV exports | `/data/exports/lineuparr_*.csv`, kept across container restarts |
| Reports | `/data/lineuparr_reports/lineuparr_report_*.html` and `*.csv`, eight of each kept |
| Report count | `/data/lineuparr/report_count.json`, read by Newsflasharr |
| Plugin directory | `/data/plugins/lineuparr/` inside the Dispatcharr data volume |
| Built-in lineup files | the plugin directory, named `{CC}_{Provider}_lineup.json` |
| Imported lineup files | `/data/lineuparr/lineups/{CC}_{Provider}_lineup.json`, kept across plugin reinstalls and container restarts |
| Logs | `docker logs dispatcharr \| grep "Lineuparr"` |
