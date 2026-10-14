import { test as base } from '@playwright/test';

/** Workflow checks use system fonts so third-party availability cannot stall navigation. */
export const test = base.extend({
  context: async ({ context }, use) => {
    await context.route(/^https:\/\/fonts\.(googleapis|gstatic)\.com\//, (route) =>
      route.abort('blockedbyclient'),
    );
    await use(context);
  },
});

export { expect } from '@playwright/test';
export type { BrowserContext, Page } from '@playwright/test';
