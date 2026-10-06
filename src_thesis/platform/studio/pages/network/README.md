# Grid & Participants page

One page with two stages and one shared network plot. Routes: `/build/grid`
(stage 1) and `/build/participants` (stage 2); switching stage in the page does
not reload anything, and a saved change reloads onto the same stage.

## The two stages

1. **Grid**: pick the network, read its facts, run a power-flow preview (colours the
   plot by voltage), list its elements (click a bus to filter), set the grid rules.
2. **Participants**: place the agents on the same plot (pink rings, blue squares for
   buses that could be participants, a filled mark for the selected one), edit them,
   preview their profiles, set the time window. Participants belong to the network
   saved in the draft, so stage 2 asks you to apply a newly picked network first.

## Files

| File | Role |
|---|---|
| `page.py` | The routes, the stage switch, the layout: slots beside and below the plot |
| `view.py` | `NetworkView`: the one plot, the loaded network, what both stages mark on it |
| `grid_stage.py` | Stage 1 controls and the draft's `grid` section |
| `participants_stage.py` | Stage 2 controls and the draft's `participants` and `time` sections |

## Flow

```
page.py            builds NetworkView and the two slots, calls the stage builders
grid_stage.py      network picked -> view.load() -> plot, elements; preview -> view.voltages
participants_stage.py   view loaded -> flexible buses, profile catalogue; plot click -> select
view.py            redraw(): topology_figure + rings, squares, selection
```

## Shared with other pages

`studio/components/network.py` (picker, summary, elements table, also used by
Inspect), `components/charts.py` (`topology_figure`), `components/participant_editor.py`,
`studio/forms.py` (`DraftForm`), services `grid`, `participants`, `profiles`, `config`.

## Typical changes

- New grid rule: `grid_stage.py` (`_settings`) and the file section in `kernel/models/sections.py`.
- New participant field: `components/participant_editor.py`, `participants_stage.py`, `kernel/models/sections.py`.
- Something else on the plot: `view.py`.
