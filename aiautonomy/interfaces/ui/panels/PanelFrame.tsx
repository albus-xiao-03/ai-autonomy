import type { ComponentChildren } from 'preact';
import { panelNumber, type PanelDefinition } from './registry';

export function PanelFrame({
  panel,
  children,
}: {
  panel: PanelDefinition;
  children: ComponentChildren;
}) {
  const labelId = `panel-${panel.key}-label`;
  return (
    <section class="panel" aria-labelledby={labelId} data-panel={panel.key}>
      <h2 class="panel-label" id={labelId}>
        <span class="panel-number">{panelNumber(panel)}</span> · {panel.title}
      </h2>
      {children}
    </section>
  );
}
