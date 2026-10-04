# Main Sunmeadow P0 CC0 stand-ins

`manifest.json` supplies five verified static stand-ins for the existing blueprint anchors. Sources are preserved under `source/`, with licence files, hashes and the approved official Kenney Nature archive. Runtime files use `EXT_meshopt_compression`; cart and windmill share an embedded KTX2 palette.

| ID | Anchors | Height | LOD triangles |
|---|---|---:|---|
| blueprint_cc0_palm | PL1:8cove+2pier |7m|336/336/336|
| blueprint_cc0_tent | ST3:two tents |2.3m|232/232/232|
| blueprint_cc0_cart | C2/C3 |1.6m|1028/1022/1022|
| blueprint_cc0_windmill | ST1 |11m|2364/2360/2360|
| blueprint_cc0_guardian | S1/S2 |6m|5005/3533/2697|

Root owns placements, loader, dynamics and physics. Bounds are centred at the feet; proxy metadata is not collider admission. Windmill sails remain separate at `windmill_sails`; palms expose rooted frond wind metadata. Implement animation once, not through competing drivers.

Missing: licensed sheep for F1, coconuts on the palm source. ST4 is supplied by the root stone-kit lane. Stand-ins do not establish final art fidelity, native renderer acceptance or device performance. Palm draw/detail limits remain a production-quality exception, not a passed tree budget.

Guardian provenance is MakeHuman CC0 graphical anatomy with existing owner-authored project cloth/ornaments; this internal reuse does not claim a new external redistributable licence for the owner's derivative work.
