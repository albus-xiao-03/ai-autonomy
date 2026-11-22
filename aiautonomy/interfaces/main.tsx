import '@fontsource-variable/geist';
import '@fontsource-variable/geist-mono';
import './styles.css';
import { render } from 'preact';
import { installDebugHandle } from './debug';
import { Session } from './net/session';
import { startTelemetry } from './net/telemetry';
import { Viewport } from './render/viewport';
import { App } from './ui/App';

function engineSocketUrl(location: Location): string {
  return `${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/ws`;
}

const root = document.getElementById('app');
if (root === null) throw new Error('missing #app element');

const session = new Session({ url: engineSocketUrl(window.location) });
const viewport = new Viewport(session);
render(<App session={session} viewport={viewport} />, root);
session.start();
startTelemetry({
  frames: viewport.frameStats,
  latency: session.commands.latency,
  isOpen: () => session.connection === 'open',
  send: (body) => {
    void session.commands.send(body);
  },
});
installDebugHandle(session, viewport);
