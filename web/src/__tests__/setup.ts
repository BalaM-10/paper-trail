import "@testing-library/jest-dom/vitest";
import { webcrypto } from "node:crypto";

// jsdom's `crypto` has no `subtle`. The browser build uses the real Web
// Crypto API; in tests we hand it Node's implementation of the same API.
if (!globalThis.crypto || !globalThis.crypto.subtle) {
  Object.defineProperty(globalThis, "crypto", { value: webcrypto, configurable: true });
}
