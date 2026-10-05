import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Testing Library only auto-cleans when vitest runs with `globals: true`; we do not, so unmount
// everything after each test or one test's DOM leaks into the next.
afterEach(() => cleanup());
