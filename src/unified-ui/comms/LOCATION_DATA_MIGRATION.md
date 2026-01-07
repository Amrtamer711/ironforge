# Location Data Migration - What We Need

Each company provides their own Excel file + files.

---

## Per Company: One Excel + Two Folders

```
backlite_dubai/
├── backlite_dubai.xlsx       <- Excel with location info
├── templates/                <- PowerPoint files for proposals
│   ├── dubai_gateway.pptx
│   └── mall_entrance.pptx
└── photos/                   <- Billboard photos for mockups
    ├── dubai_gateway.jpg
    └── mall_entrance.jpg
```

Same structure for: `backlite_uk/`, `backlite_abudhabi/`, `viola/`

---

## Excel Columns

### Required for ALL locations

| Column | What to Put | Example |
|--------|-------------|---------|
| location_key | Unique ID (lowercase, no spaces) | `dubai_gateway` |
| display_name | Client-facing name | `Dubai Gateway` |
| type | `digital` or `static` | `digital` |
| city | City name | `Dubai` |
| country | Country | `UAE` |

### For DIGITAL screens only

| Column | What to Put | Example |
|--------|-------------|---------|
| width_pixels | Screen width in pixels | `1920` |
| height_pixels | Screen height in pixels | `1080` |
| spots_in_loop | How many ads per rotation | `6` |
| loop_seconds | Full loop duration | `60` |

### For STATIC billboards only

| Column | What to Put | Example |
|--------|-------------|---------|
| width_meters | Width in meters | `12` |
| height_meters | Height in meters | `4` |
| illumination | `frontlit`, `backlit`, or `none` | `backlit` |

### Optional (nice to have)

| Column | What to Put |
|--------|-------------|
| address | Street address |
| description | Brief description |
| gps_lat | GPS latitude |
| gps_lng | GPS longitude |

---

## What Each Feature Needs

### Proposals (generating PDF quotes)

**Needs:**
1. Excel row with `location_key` and `display_name`
2. PowerPoint template in `templates/` folder named `{location_key}.pptx`

**Example:** To generate proposals for "Dubai Gateway":
- Excel has row with `location_key = dubai_gateway`
- File exists: `templates/dubai_gateway.pptx`

---

### Mockups (putting artwork on billboard photos)

**Needs:**
1. Excel row with `location_key`
2. Photo of billboard in `photos/` folder named `{location_key}.jpg`

**Example:** To generate mockups for "Dubai Gateway":
- Excel has row with `location_key = dubai_gateway`
- File exists: `photos/dubai_gateway.jpg`

*Note: After upload, we mark the screen area in the UI - you just provide the photo.*

---

### Video Critique (approval workflows)

**Needs:**
- Just the location name as text (entered when creating tasks)
- No special data required in advance

---

## Example Excel Rows

| location_key | display_name | type | city | country | width_pixels | height_pixels | spots_in_loop |
|--------------|--------------|------|------|---------|--------------|---------------|---------------|
| dubai_gateway | Dubai Gateway | digital | Dubai | UAE | 1920 | 1080 | 6 |
| mall_entrance | Mall Entrance LED | digital | Dubai | UAE | 3840 | 2160 | 8 |
| szr_static | SZR Highway Billboard | static | Dubai | UAE | | | |

For the static one, add: `width_meters = 12`, `height_meters = 4`, `illumination = backlit`

---

## File Naming Rules

**IMPORTANT:** The `location_key` in Excel MUST match the file names exactly.

| location_key in Excel | Template File | Photo File |
|-----------------------|---------------|------------|
| `dubai_gateway` | `dubai_gateway.pptx` | `dubai_gateway.jpg` |
| `mall_entrance` | `mall_entrance.pptx` | `mall_entrance.jpg` |

---

## Checklist Per Location

- [ ] Row in Excel with basic info
- [ ] Template file (for proposals)
- [ ] Photo file (for mockups)
- [ ] File names match location_key

---

## Questions?

If unsure about a field, leave it blank and add a note. The essential ones are:
- **location_key** (must be unique, lowercase, underscores)
- **display_name** (what clients see)
- **type** (digital or static)
- **city/country**

Everything else can be filled in later.
