// Generate aiautonomy/interfaces/net/protocol.gen.ts from the engine's exported JSON Schema
// (plans/R1.md §4.8). Run from the repository root:
//
//   npm run gen:protocol    regenerate the committed file
//   npm run check:protocol  regenerate into a temp file and exit 1 on drift
//
// REQ: ARCH-03
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const here = dirname(fileURLToPath(import.meta.url));
const SCHEMA = resolve(here, '../../engines/api/protocol.schema.json');
const OUTPUT = resolve(here, 'protocol.gen.ts');

const BANNER = `/* eslint-disable */
/**
 * Generated — do not edit.
 * Source: aiautonomy/engines/api/protocol.schema.json (the engine's pydantic protocol models).
 * Regenerate with \`make protocol\` or \`npm run gen:protocol\`; CI checks for drift.
 */`;

async function generate() {
  if (!existsSync(SCHEMA)) {
    console.error(`protocol: schema not found at ${SCHEMA}; export it with \`make protocol\``);
    process.exit(1);
  }
  const schema = JSON.parse(await readFile(SCHEMA, 'utf8'));
  const ts = await compile(schema, 'Protocol', {
    bannerComment: BANNER,
    additionalProperties: false,
    unreachableDefinitions: true,
    cwd: dirname(SCHEMA),
    style: { singleQuote: true, printWidth: 100 },
  });
  return ts.replace(/\r\n/g, '\n');
}

const check = process.argv.includes('--check');
const generated = await generate();

if (!check) {
  await mkdir(dirname(OUTPUT), { recursive: true });
  await writeFile(OUTPUT, generated);
  console.log(`protocol: wrote ${OUTPUT}`);
} else {
  const dir = await mkdtemp(join(tmpdir(), 'aia-protocol-'));
  try {
    const fresh = join(dir, 'protocol.gen.ts');
    await writeFile(fresh, generated);
    const committed = existsSync(OUTPUT) ? await readFile(OUTPUT, 'utf8') : '';
    if (committed !== (await readFile(fresh, 'utf8'))) {
      console.error(
        'protocol: aiautonomy/interfaces/net/protocol.gen.ts is out of date with aiautonomy/engines/api/protocol.schema.json; run `make protocol`',
      );
      process.exitCode = 1;
    } else {
      console.log('protocol: aiautonomy/interfaces/net/protocol.gen.ts is up to date');
    }
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}
