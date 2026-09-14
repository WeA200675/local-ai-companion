# Local media workflow profiles

A single ComfyUI workflow is often not ideal for every visual. The app can therefore route one media intent across multiple user-owned local workflows.

## Why profiles exist

A fast still-image workflow can be used for ordinary visuals, a slower identity-focused workflow can be used when the recurring companion character matters, and a motion workflow can be used when the planner asks for a GIF or video loop.

The language model chooses only the media intent (`image`, `gif`, or `video`) and whether the recurring character is part of the scene. Deterministic application code then selects the best configured workflow profile. This keeps the routing inspectable and prevents the model from inventing arbitrary local file paths or node ids.

## Catalog format

Set **Workflow-Profile** in Settings to a local JSON file. Relative workflow paths are resolved relative to that catalog file.

```json
{
  "version": 1,
  "profiles": [
    {
      "id": "still",
      "label": "Fast still",
      "kinds": ["image"],
      "workflow": "workflows/still_api.json",
      "positive_node": "6",
      "negative_node": "7",
      "seed_node": "3",
      "priority": 10
    },
    {
      "id": "character",
      "label": "Character detail",
      "kinds": ["image"],
      "workflow": "workflows/character_api.json",
      "positive_node": "6",
      "negative_node": "7",
      "seed_node": "3",
      "reference_node": "12",
      "reference_input_key": "image",
      "prefer_for_character": true,
      "priority": 5
    },
    {
      "id": "motion",
      "label": "Short local motion",
      "kinds": ["gif", "video"],
      "workflow": "workflows/motion_api.json",
      "positive_node": "6",
      "negative_node": "7",
      "seed_node": "3"
    }
  ]
}
```

## Routing

Only enabled profiles whose workflow file exists and whose `kinds` contain the requested media kind are eligible. `priority` is the base score. When a recurring character is requested, `prefer_for_character` receives a strong routing bonus. If a usable local reference image exists, a profile with a configured reference input receives an additional bonus.

If no profile matches, the existing standard workflow remains the fallback when it is configured. The selected profile id is stored with the local media-history record so the routing decision remains visible later.

## Diagnostics and privacy

**Lokale Verbindungen testen** validates the catalog, unique profile ids, referenced workflow files, prompt/seed nodes, and configured reference inputs. All catalog files, workflows, reference images, and generated outputs remain local. No workflow or media file is uploaded by this feature.

Profile workflows should keep all depicted people clearly adult. The app's visual planner remains limited to non-graphic adult/suggestive imagery even when a local workflow is technically capable of more.
