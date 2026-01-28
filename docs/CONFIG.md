# LabelOps Configuration (Module 6)

## Location
The default configuration file lives at:

```
D:\LabelOps\config\clients.yaml
```

You can override the path by calling `load_config(path=...)` from `app/config.py`.

## Adding a new client
1. Copy an existing `client_XX` block.
2. Ensure the client ID matches the format `client_01`, `client_02`, etc.
3. Fill in:
   - `display_name`
   - `defaults` (at least `service` and `weight_kg`)
   - `services` with triggers
   - `clickdrop` with `template_path` and `column_mapping`
   - optional `folders`

## Sections explained
### `defaults`
Defines the baseline values used when no override is found in the raw shipment text.

Common defaults:
- `service`: e.g. `T24`
- `weight_kg`: numeric weight in kilograms
- `country`: e.g. `UNITED KINGDOM`

### `services`
Defines allowed service names and how each service is triggered.

Each service has:
- `name`: the friendly service name.
- `code`: optional backend code if required by your carrier.
- `trigger`:
  - `type: "default"` means this service is used when no tag is present.
  - `type: "tag"` means the service is selected when a matching tag is found.
  - `tag`: the tag value for `type: "tag"`.

### `clickdrop`
Defines the Excel import template and column mapping.

- `template_path`: where the Click & Drop template file lives.
- `column_mapping`: 1-indexed Excel column positions (headerless).
  - Required fields: `full_name`, `address_line_1`, `address_line_2`, `town_city`,
    `county`, `postcode`, `country`, `service`, `weight_kg`.
  - Optional fields: `reference`, `phone`, `email`.

### `folders`
Optional per-client folder overrides. If omitted, defaults are used:

```
D:\LabelOps\Clients\<client_id>\IN_TXT
D:\LabelOps\Clients\<client_id>\READY_XLSX
D:\LabelOps\Clients\<client_id>\ARCHIVE
D:\LabelOps\Clients\<client_id>\TRACKING_OUT
```

## Service tag usage
Tag-based services are activated when a tag appears in the raw text. You can place tags:

- On the first line:
  - `SD`
  - `SERVICE=SD`
- Inline with other tokens:
  - `... Notes: SD ...`
  - `... [SD] ...`

Any matching tag triggers the corresponding service rule. If no tag is found, the
`default` service is used.
