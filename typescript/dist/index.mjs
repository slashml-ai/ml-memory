import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const cjs = require("./index.js");

export const {
  DEFAULT_BASE_URL,
  DEFAULT_MODEL,
  DEFAULT_TIMEOUT_MS,
  SlashMLAPIError,
  ProjectManager,
  MemoryClient,
  Memory,
  AsyncMemoryClient,
  AsyncMemory,
  SlashMLMemory,
  SlashMLClient,
  AsyncSlashMLMemory,
  AsyncSlashMLClient,
} = cjs;

export default cjs;
