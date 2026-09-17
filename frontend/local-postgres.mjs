import EmbeddedPostgres from "embedded-postgres";
import { existsSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
const dir = fileURLToPath(new URL("../data/postgres", import.meta.url));
mkdirSync(dir, { recursive: true });
const pg = new EmbeddedPostgres({
  databaseDir: dir,
  user: "meridian",
  password: "meridian",
  port: 54329,
  persistent: true,
  postgresFlags: ["-c", "listen_addresses=127.0.0.1"],
  onLog: () => {},
  onError: (m) => {
    if (String(m).includes("FATAL")) console.error(m);
  },
});
if (!existsSync(dir + "/PG_VERSION")) await pg.initialise();
await pg.start();
const client = pg.getPgClient();
await client.connect();
const found = await client.query(
  "SELECT 1 FROM pg_database WHERE datname = 'meridian'",
);
if (!found.rowCount) await pg.createDatabase("meridian");
await client.end();
console.log(
  "Connact.ai PostgreSQL ready on 127.0.0.1:54329 (persistent local database).",
);
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, async () => {
    await pg.stop();
    process.exit(0);
  });
setInterval(() => {}, 60000);
