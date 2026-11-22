// The VIS-04 panels by spec number. Later milestones register panels 1, 2 and 4-10 here.
// REQ: VIS-04
import type { ComponentType } from 'preact';
import type { Session } from '../../net/session';
import { PlaybackPanel } from './PlaybackPanel';

export interface PanelProps {
  readonly session: Session;
}

export interface PanelDefinition {
  /** Number in the VIS-04 list (1 run configuration ... 10 final outcome report). */
  readonly number: number;
  readonly key: string;
  readonly title: string;
  readonly component: ComponentType<PanelProps>;
}

export const PANELS: readonly PanelDefinition[] = [
  { number: 3, key: 'playback', title: 'playback', component: PlaybackPanel },
];

/** The numbered mono label, e.g. `03`. */
export function panelNumber(panel: PanelDefinition): string {
  return String(panel.number).padStart(2, '0');
}
