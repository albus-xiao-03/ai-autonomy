# Borough

An arcade city builder in the browser, using the Boston area from the shared reference.

## Run locally

    python3 -m http.server 8712 --bind 127.0.0.1 --directory dist

Open http://127.0.0.1:8712. Ollama serves the downloaded qwen3:8b model on localhost:11434. The mayor chooses district responses and generates public explanations through the native Ollama chat endpoint. The clock holds during requests. An identified civic controller handles model failures.

## Play

Level 1 starts near City Hall with Beacon Hill homes and Government Center offices. Their gold access points need local roads. Connect that network to the fixed entry highway, then run a day and get every resident to work and home. The Next level button unlocks a larger map when the day finishes successfully. Existing roads carry forward.

Level 2 adds the West End and North End. Level 3 opens the river crossing to Kendall Square, the Financial District and Waterfront. Level 4 opens Charlestown. Neighborhoods use fixed illustrative building clusters.

Select highway, one-way or two-way roads. Highways have two lanes in each direction. Two-way roads have one lane in each direction. One-way travel follows the drawing direction. Choose Click points or Drag road in the drawing selector. Click a selected tool again to deselect it. Move map also deselects tools. Drag the map to pan and use the wheel to zoom around the pointer. Shift drag pans while a road tool is selected. Escape ends the road and switches to moving.

Bridge over water works with all three road types. Both bridge endpoints must be on dry land. Bridges use raised decks, ramps, railings and supports. Traffic uses them within the same route network.

Road endpoints snap to neighborhood access points and other roads. Neighborhood access needs a clear connection within 20 meters of the road curb. Light driveways confirm access. Orange markers indicate missing access. Road access help explains the rule. Neighborhoods and landmarks are fixed. Bulldoze removes player roads. Undo reverses the latest edit.

Keyboard controls on the map use arrows for 25-meter cursor movement and Shift arrows for five-meter movement. Enter places an endpoint. With Move map selected, arrows pan the view.

Rush-hour through traffic enters and exits along the fixed highway, following that route through the city. It appears during the morning and evening peaks and is counted separately from neighborhood residents. The model uses scheduled traffic flow. Individual vehicle collision and queue simulation remains a later refinement.

The mayor's thought bubble opens the public explanations, orders and outcomes. Model-generated orders are labeled Qwen. Resident routines follow the directed player road network, including driveway access. Leisure trips occur only when a usable route exists.

## Geography

The map crop spans longitude -71.085 to -71.045 and latitude 42.354 to 42.378. The current requested scale is 1:1 in real-world meters, using a local equirectangular projection around 42.366 N, 71.065 W. The scale bar reports 100 meters.

Land comes from the Boston municipality boundary service, including Cambridge and Somerville. MassGIS hydrography supplies the water boundaries. Geometry has approximately 1.5-meter simplification tolerance at the original import scale. The source resolution generalizes some shore details.

Landmarks use geographic center coordinates with simplified low-poly models and approximate dimensions. Neighborhood clusters are arcade representations at real neighborhood locations. Exact surveyed building footprints and elevations remain a future accuracy pass.

Sources:
- https://services2.arcgis.com/d0NFID1O0ng4wccB/ArcGIS/rest/services/Boston_Municipality_Boundary/FeatureServer
- https://www.mass.gov/info-details/massgis-data-massdep-hydrography-125000
- https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services/Massachusetts_Water_Features/FeatureServer

The browser saves progress under borough-levels-v1. Earlier free-placement and arcade saves remain under their previous keys. Timed building deliveries and additional disaster scenarios are pending.
