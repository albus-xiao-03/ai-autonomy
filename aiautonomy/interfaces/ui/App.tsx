import type { Session } from '../net/session';
import type { Viewport } from '../render/viewport';
import { FpsMeter } from './FpsMeter';
import { Inspector } from './Inspector';
import { MapCanvas } from './MapCanvas';
import { PanelFrame } from './panels/PanelFrame';
import { PANELS } from './panels/registry';
import { TopBar } from './TopBar';
import { ViewControls } from './ViewControls';

export function App({ session, viewport }: { session: Session; viewport: Viewport }) {
  return (
    <div class="app">
      <MapCanvas viewport={viewport} />
      <TopBar session={session} />
      <aside class="panel-stack" aria-label="Panels">
        {PANELS.map((panel) => (
          <PanelFrame key={panel.key} panel={panel}>
            <panel.component session={session} />
          </PanelFrame>
        ))}
      </aside>
      <Inspector session={session} />
      <div class="hud-corner hud-left">
        <FpsMeter stats={viewport.frameStats} />
      </div>
      <div class="hud-corner hud-right">
        <ViewControls viewport={viewport} />
      </div>
    </div>
  );
}
