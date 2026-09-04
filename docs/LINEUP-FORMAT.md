# Lineup file format

A lineup file is a list of the channels a TV provider carries, with their channel
numbers, grouped into categories. It holds names and numbers only: no stream
addresses, no credentials, no provider account details.

Lineuparr matches the names in this file against the stream names Dispatcharr
already holds for your own sources.

| Also available | |
|---|---|
| [Project front page](../README.md) | what the plugin is and how to install it |
| [User guide](USER-GUIDE.md) | settings, actions, troubleshooting |

---

## The minimum

```json
{
  "package": "Provider Name",
  "date": "2026-01-01",
  "description": "Description of the lineup",
  "source": "Where the lineup data came from",
  "categories": {
    "News": [
      { "name": "CNN", "number": 202 },
      { "name": "Fox News", "number": 360 }
    ],
    "Sports": [
      { "name": "ESPN", "number": 206 }
    ]
  }
}
```

`categories` is the only required key. `package`, `date`, `description` and
`source` are shown in the interface and in the lineup dropdown.

## The filename decides the country

The file must be named `{CC}_{Provider}_lineup.json`, where `{CC}` is a
two-letter ISO country code: `US_MyProvider_lineup.json`,
`UK_Freeview_lineup.json`.

The country code does two jobs. It selects the country directory when logos are
matched against the [tv-logos](https://github.com/tv-logo/tv-logos) repository,
and it is the default country for every channel in the file, which is what stops
a foreign stream attaching to one of these channels.

Hyphens in the provider part become spaces in the dropdown label, so
`US_Verizon-FIOS_lineup.json` reads as "Verizon FIOS (US)".

Place a manually managed file in the plugin directory, `/data/plugins/lineuparr/`, or in the persistent lineup directory, `/data/lineuparr/lineups/`, and it appears in the **Lineup File** dropdown. Files in the persistent directory are labeled **Imported:** and survive plugin reinstalls.

For an HTTP or HTTPS source such as GraceNoteScraper, save the endpoint in **Generated Lineup URL** and run **Import / Refresh Generated Lineup**. The response must use this same filename format in its `Content-Disposition` header or URL path. Lineuparr validates the document and atomically recreates the persistent copy.

---

## Per-channel aliases

A channel entry may carry its own `aliases` array. These are merged with the
built-in alias table for this lineup only, which makes it the right home for
stream-name variants specific to one provider, rather than adding them globally.

```json
{ "name": "My9 New York", "number": 509, "aliases": ["WWOR", "WWOR-TV", "MY9"] }
```

A single alias may be given as a plain string instead of a one-item list.

**Callsign aliases reach into longer names.** When an alias is a US broadcast
callsign, a stream carrying that callsign anywhere in its name matches, so
`WWOR` reaches `US: MY 9 WWOR NEW YORK` and `CITY: MNT WWOR NEW YORK` even
though the channel is called "My9 New York". Ordinary English words that happen
to have callsign shape (KIDS, WORLD, WOMEN, WEST, KISS) are excluded, so they
never pull in unrelated streams.

Only an alias that is *entirely* a callsign counts. `WWOR` and `WWOR-TV` do;
`WWOR New York` does not, because a display name is not a claim about which
streams belong to the channel.

---

## Foreign channels inside a single-country lineup

Matching is restricted to the lineup's own country. To carry a block of foreign
channels anyway, mark them. There are two ways, and you can use both in one file.

### A country prefix on the channel name

Name the channel `{CC}_{Name}`. It is then matched against that country instead
of the lineup's, wherever it sits:

```json
"International": [
  { "name": "UK_CNN", "number": 501 },
  { "name": "FR_TF1", "number": 502 }
]
```

The prefix is stripped before anything else sees it, so Dispatcharr creates the
channel as `CNN`, not `UK_CNN`, and the matcher looks for "CNN". Each marked
channel also gets that country's aliases.

Only recognized country codes count, so an ordinary name that happens to contain
an underscore, such as `MTV_Live`, is left exactly as written. A name with
nothing after the prefix is also left alone.

### A country prefix on the category name

A whole category can be marked instead: `UK| International`, `UK: International`
or `UK International`. Use this when the foreign channels are already grouped
together.

### Which one wins

A channel's own prefix beats its category's, which beats the lineup filename.
When a channel's prefix overrides the others, the plugin logs it, so a channel
that unexpectedly matches nothing can be traced.

### What this cannot do

The country filter drops a stream whose name carries a *different* country
marker, and keeps a stream with no marker at all. So a `UK_` channel is still
eligible for an untagged stream. Marking a channel decides which country is
filtered for; it cannot make the filter more certain than the stream names allow.

---

## Contributing a lineup

Community-contributed lineups are welcome. Open a pull request with the file, or
open an issue including the provider name, the country, the channel list with
numbers and categories, and where the listing came from.

If you would like a provider added but cannot build the file yourself, open a
**Lineup Request** issue with the provider name, the country, and a link to their
public channel listing page.
